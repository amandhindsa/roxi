from __future__ import annotations

import json
import logging

from roxi.agents.drafter import draft_email
from roxi.agents.extractor import extract
from roxi.agents.researcher import research_company
from roxi.agents.scorer import score
from roxi.collectors import job_boards, registry, reddit
from roxi.config import VerticalConfig
from roxi.dedupe import dedupe_company, dedupe_exact, signal_key
from roxi.delivery import deliver
from roxi.models import Lead, RawItem, Signal
from roxi import store
from roxi.telemetry import emit

log = logging.getLogger(__name__)


def _collect_all(vertical: VerticalConfig, run_id: str | None = None,
                 subscription_id: str | None = None) -> list[RawItem]:
    raw: list[RawItem] = []
    for collector in (job_boards, registry, reddit):
        try:
            items = collector.fetch(vertical)
            # Record source health per subscription
            if subscription_id:
                try:
                    store.record_source_health(
                        subscription_id=subscription_id,
                        source_name=collector.__name__.split(".")[-1],
                        count=len(items),
                    )
                except Exception:
                    pass  # source health is observability, not critical path
            emit("collector.run", run_id=run_id, vertical_id=vertical.vertical_id,
                 agent=collector.__name__, data={"items": len(items)})
            raw.extend(items)
        except NotImplementedError:
            pass
        except Exception as exc:
            log.error("collector %s failed: %s", collector.__name__, exc)
            emit("collector.error", run_id=run_id, vertical_id=vertical.vertical_id,
                 agent=collector.__name__, data={"error": str(exc)}, level="error")
    return raw


def _check_spend_ceiling(subscription_id: str | None, ceiling: float) -> bool:
    """Returns True if there is budget remaining (run should proceed)."""
    if not subscription_id or ceiling <= 0:
        return True
    try:
        spent = store.get_subscription_spend_today(subscription_id)
        if spent >= ceiling:
            log.warning(
                "pipeline: subscription %s has spent $%.4f today (ceiling $%.2f) — skipping run",
                subscription_id, spent, ceiling,
            )
            return False
    except Exception as exc:
        log.warning("pipeline: could not check spend ceiling: %s", exc)
    return True


def run(
    vertical: VerticalConfig,
    org_id: str | None = None,
    subscription_id: str | None = None,
    spend_ceiling_usd: float = 0.0,
) -> list[Lead]:
    store.init_db()

    # Enforce spend ceiling before doing any work
    if not _check_spend_ceiling(subscription_id, spend_ceiling_usd):
        return []

    run_id = store.start_run(vertical.vertical_id, org_id=org_id, subscription_id=subscription_id)
    log.info("run %s started for %s (org_id=%s, subscription_id=%s)",
             run_id, vertical.vertical_id, org_id, subscription_id)
    emit("run.start", run_id=run_id, vertical_id=vertical.vertical_id,
         data={"org_id": org_id, "subscription_id": subscription_id})

    raw_items = _collect_all(vertical, run_id=run_id, subscription_id=subscription_id)
    log.info("collected %d raw items (run_id=%s)", len(raw_items), run_id)

    # Each tuple carries (raw_idx, raw, signal/scored) so item_seq is the original
    # position in raw_items throughout all stages — enabling end-to-end stage tracing.
    signals: list[tuple[int, RawItem, object]] = []
    for raw_idx, raw in enumerate(raw_items):
        sig = extract(raw, vertical, run_id=run_id)
        if sig is not None:
            signals.append((raw_idx, raw, sig))
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="extract", status="passed",
                payload_json=sig.model_dump_json(),
                source_url=raw.source_url, company=sig.company,
            )
        else:
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="extract", status="dropped",
                drop_reason="extraction_failed",
                drop_detail=raw.title[:120] if raw.title else None,
                source_url=raw.source_url,
            )

    log.info("extracted %d signals from %d items (run_id=%s)", len(signals), len(raw_items), run_id)

    # Dedupe is subscription-scoped so two customers in the same vertical
    # don't suppress each other's leads.
    seen_keys = store.seen_dedupe_keys(subscription_id=subscription_id)
    recent_names = store.recent_company_names(days=30)

    # Exact dedupe first (cheap — no LLM calls)
    signal_objects = [s for _, _, s in signals]
    exact_deduped = dedupe_exact(signal_objects, seen_keys)
    exact_set = {signal_key(s) for s in exact_deduped}

    survivors: list[tuple[int, RawItem, object]] = []
    for raw_idx, r, s in signals:
        if signal_key(s) in exact_set:
            survivors.append((raw_idx, r, s))
        else:
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="dedupe", status="dropped",
                drop_reason="duplicate_exact",
                source_url=r.source_url, company=s.company,
            )

    log.info("%d signals after exact dedupe (run_id=%s)", len(survivors), run_id)

    # Score before company dedupe so the best signal per company wins (H3)
    scored_pairs: list[tuple[int, RawItem, object]] = []
    for raw_idx, raw, sig in survivors:
        scored = score(sig, vertical, run_id=run_id)
        if scored is None:
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="score", status="dropped",
                drop_reason="scoring_failed",
                source_url=raw.source_url, company=sig.company,
            )
            continue
        store.log_stage_output(
            run_id=run_id, item_seq=raw_idx, stage="score", status="passed",
            payload_json=scored.model_dump_json(),
            source_url=raw.source_url, company=scored.company,
        )
        scored_pairs.append((raw_idx, raw, scored))

    # Sort highest score first, then company dedupe keeps the winner
    scored_pairs.sort(key=lambda x: x[2].score, reverse=True)
    scored_signals = [s for _, _, s in scored_pairs]
    company_deduped = dedupe_company(scored_signals, recent_names)
    company_set = {signal_key(s) for s in company_deduped}

    deduped_pairs: list[tuple[int, RawItem, object]] = []
    for raw_idx, r, s in scored_pairs:
        if signal_key(s) in company_set:
            deduped_pairs.append((raw_idx, r, s))
        else:
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="dedupe", status="dropped",
                drop_reason="duplicate_fuzzy",
                source_url=r.source_url, company=s.company,
            )
    scored_pairs = deduped_pairs

    log.info("%d signals after company dedupe (run_id=%s)", len(scored_pairs), run_id)

    qualified: list[tuple[int, RawItem, object]] = []
    for raw_idx, r, s in scored_pairs:
        if s.disqualified_by:
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="score", status="dropped",
                drop_reason="disqualified",
                drop_detail=s.disqualified_by,
                payload_json=s.model_dump_json(),
                source_url=r.source_url, company=s.company,
            )
        elif s.score < vertical.qualify_threshold:
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="score", status="dropped",
                drop_reason="below_threshold",
                drop_detail=f"score={s.score} threshold={vertical.qualify_threshold}",
                payload_json=s.model_dump_json(),
                source_url=r.source_url, company=s.company,
            )
        else:
            qualified.append((raw_idx, r, s))

    # Log items cut by the budget cap — raw_idx still comes from the tuple.
    for raw_idx, r, s in qualified[vertical.daily_research_budget:]:
        store.log_stage_output(
            run_id=run_id, item_seq=raw_idx, stage="score", status="dropped",
            drop_reason="over_budget",
            source_url=r.source_url, company=s.company,
        )
    qualified = qualified[:vertical.daily_research_budget]

    log.info("%d signals qualified (threshold=%d, budget=%d, run_id=%s)",
             len(qualified), vertical.qualify_threshold, vertical.daily_research_budget, run_id)

    total_cost = 0.0
    leads: list[Lead] = []

    for raw_idx, raw, scored in qualified:
        # Re-check spend ceiling before each LLM-heavy item (research + draft)
        if not _check_spend_ceiling(subscription_id, spend_ceiling_usd):
            log.info("pipeline: spend ceiling hit mid-run at item %d — stopping (run_id=%s)",
                     raw_idx, run_id)
            break

        try:
            research = research_company(scored, vertical, run_id=run_id)
            if research is None:
                log.info("pipeline: skipping %r — no research (run_id=%s)", scored.company, run_id)
                emit("lead.error", run_id=run_id, vertical_id=vertical.vertical_id,
                     data={"company": scored.company, "error": "research returned None"}, level="warning")
                store.log_stage_output(
                    run_id=run_id, item_seq=raw_idx, stage="research", status="dropped",
                    drop_reason="research_empty",
                    source_url=raw.source_url, company=scored.company,
                )
                continue

            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="research", status="passed",
                payload_json=research.model_dump_json(),
                source_url=raw.source_url, company=scored.company,
            )

            draft = draft_email(scored, research, vertical, run_id=run_id)
            if draft is None:
                log.warning("pipeline: no draft for %r (run_id=%s) — skipping", scored.company, run_id)
                store.log_stage_output(
                    run_id=run_id, item_seq=raw_idx, stage="draft", status="dropped",
                    drop_reason="draft_failed",
                    source_url=raw.source_url, company=scored.company,
                )
                continue
            store.log_stage_output(
                run_id=run_id, item_seq=raw_idx, stage="draft", status="passed",
                source_url=raw.source_url, company=scored.company,
            )

            base_signal = Signal(**{k: v for k, v in scored.model_dump().items() if k in Signal.model_fields})
            lead = Lead(
                raw=raw,
                signal=base_signal,
                scored=scored,
                research=research,
                draft=draft,
                dedupe_key=signal_key(scored),
                org_id=org_id,
                subscription_id=subscription_id,
            )
            persisted = store.save(lead, vertical.vertical_id, org_id=org_id, subscription_id=subscription_id)
            if not persisted:
                log.warning("pipeline: lead %s not persisted (dedupe collision) — skipping delivery", lead.id)
                continue
            leads.append(lead)
            emit("lead.created", run_id=run_id, vertical_id=vertical.vertical_id,
                 lead_id=lead.id, data={"company": scored.company, "score": scored.score})
        except Exception as exc:
            log.error("pipeline: error processing %r (run_id=%s): %s",
                      scored.company, run_id, exc, exc_info=True)
            emit("lead.error", run_id=run_id, vertical_id=vertical.vertical_id,
                 data={"company": scored.company, "error": str(exc)}, level="error")
            continue

    total_cost = store.get_run_cost(run_id)

    deliver(leads, vertical.vertical_id)
    log.info("delivered %d leads (run_id=%s, cost=$%.4f)", len(leads), run_id, total_cost)

    store.finish_run(
        run_id,
        raw_collected=len(raw_items),
        signals_extracted=len(signals),
        signals_qualified=len(qualified),
        leads_delivered=len(leads),
        total_cost_usd=total_cost,
    )
    emit("run.finish", run_id=run_id, vertical_id=vertical.vertical_id,
         data={"leads_delivered": len(leads), "total_cost_usd": total_cost})

    return leads
