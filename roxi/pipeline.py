from __future__ import annotations

import logging

from roxi.agents.drafter import draft_email
from roxi.agents.extractor import extract
from roxi.agents.researcher import research_company
from roxi.agents.scorer import score
from roxi.collectors import job_boards, registry, reddit
from roxi.config import VerticalConfig
from roxi.dedupe import dedupe, signal_key
from roxi.delivery import deliver
from roxi.models import Lead, RawItem
from roxi import store
from roxi.telemetry import emit

log = logging.getLogger(__name__)


def _collect_all(vertical: VerticalConfig, run_id: str | None = None) -> list[RawItem]:
    raw: list[RawItem] = []
    for collector in (job_boards, registry, reddit):
        try:
            items = collector.fetch(vertical)
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


def run(vertical: VerticalConfig, org_id: str | None = None) -> list[Lead]:
    store.init_db()
    run_id = store.start_run(vertical.vertical_id, org_id=org_id)
    log.info("run %s started for %s (org_id=%s)", run_id, vertical.vertical_id, org_id)
    emit("run.start", run_id=run_id, vertical_id=vertical.vertical_id,
         data={"org_id": org_id})

    raw_items = _collect_all(vertical, run_id=run_id)
    log.info("collected %d raw items (run_id=%s)", len(raw_items), run_id)

    signals = []
    for raw in raw_items:
        sig = extract(raw, vertical, run_id=run_id)
        if sig is not None:
            signals.append((raw, sig))

    log.info("extracted %d signals from %d items (run_id=%s)", len(signals), len(raw_items), run_id)

    seen_keys = store.seen_dedupe_keys()
    recent_names = store.recent_company_names(days=30)

    signal_objects = [s for _, s in signals]
    deduped = dedupe(signal_objects, seen_keys, recent_names)
    deduped_set = {signal_key(s) for s in deduped}

    survivors = [(r, s) for r, s in signals if signal_key(s) in deduped_set]
    log.info("%d signals after dedupe (run_id=%s)", len(survivors), run_id)

    scored_pairs = []
    for raw, sig in survivors:
        scored = score(sig, vertical, run_id=run_id)
        if scored is None:
            continue  # ExtractionError — signal skipped, not added to dedup keys
        scored_pairs.append((raw, scored))

    qualified = [
        (r, s) for r, s in scored_pairs
        if not s.disqualified_by and s.score >= vertical.qualify_threshold
    ]
    qualified = qualified[:vertical.daily_research_budget]
    log.info("%d signals qualified (threshold=%d, budget=%d, run_id=%s)",
             len(qualified), vertical.qualify_threshold, vertical.daily_research_budget, run_id)

    total_cost = 0.0
    leads: list[Lead] = []

    for raw, scored in qualified:
        try:
            research = research_company(scored, vertical, run_id=run_id)
            if research is None:
                log.info("pipeline: skipping %r — no research (run_id=%s)", scored.company, run_id)
                emit("lead.error", run_id=run_id, vertical_id=vertical.vertical_id,
                     data={"company": scored.company, "error": "research returned None"}, level="warning")
                continue

            draft = draft_email(scored, research, vertical, run_id=run_id)

            # signal = the pre-scoring Signal fields; scored = the full ScoredSignal
            from roxi.models import Signal
            base_signal = Signal(**{k: v for k, v in scored.model_dump().items() if k in Signal.model_fields})
            lead = Lead(
                raw=raw,
                signal=base_signal,
                scored=scored,
                research=research,
                draft=draft,
                dedupe_key=signal_key(scored),
            )
            store.save(lead, vertical.vertical_id)
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
