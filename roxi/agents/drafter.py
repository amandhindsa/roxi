from __future__ import annotations

import json
import logging

from roxi.config import VerticalConfig
from roxi.llm import ExtractionError, structured
from roxi.models import EmailDraft, ResearchBrief, ScoredSignal

log = logging.getLogger(__name__)

_SYSTEM = """\
You write first-touch cold emails for a sales team. The recipients are operations managers \
and owners at trucking companies. They delete marketing email on sight. \
Your job is to get a reply, not to sell.

Rules:
- Open with the specific researched fact about this company — not with who we are.
- Stay under 120 words total.
- Make one concrete product claim tied to their situation.
- End with one small ask: a reply, not a demo or a call.
- No greeting filler. No words like "seamless", "streamline", "leverage", "excited".
- Do not add any detail that is not in the brief or signal.
- If confidence is low, write a shorter email with fewer claims, not a longer padded one.
- hook_used: name the specific researched fact you opened with.

Product: {product_brief}
"""


def draft_email(
    scored: ScoredSignal,
    research: ResearchBrief | None,
    vertical: VerticalConfig,
    run_id: str | None = None,
) -> EmailDraft | None:
    if research is None:
        log.debug("drafter: skipping %r — no research (run_id=%s)", scored.company, run_id)
        return None

    rules_summary = ", ".join(
        f"{r.rule} (+{r.delta})" for r in scored.rules_fired
    )
    hooks_list = "\n".join(f"- {h}" for h in research.hooks) if research.hooks else "None found"

    user = f"""\
Signal:
  Company: {scored.company}
  Location: {scored.location}
  Signal type: {scored.signal_type}
  Evidence: {scored.evidence}
  Score: {scored.score}/100 — rules fired: {rules_summary}

Research brief (confidence: {research.confidence}):
  Summary: {research.company_summary}
  Fleet estimate: {research.fleet_estimate or "unknown"}
  Operating lanes: {", ".join(research.operating_lanes) or "unknown"}
  Current stack: {research.current_stack_guess or "unknown"}
  Decision-maker title: {research.decision_maker_title or "unknown"}
  Hooks:
{hooks_list}

Write the EmailDraft."""

    try:
        draft = structured(
            model=vertical.models.drafter,
            system=_SYSTEM.format(product_brief=vertical.product_brief.strip()),
            user=user,
            schema=EmailDraft,
            agent="drafter",
            run_id=run_id,
        )
        log.info("drafter: draft ready for %r hook=%r (run_id=%s)", scored.company, draft.hook_used, run_id)
        return draft
    except ExtractionError as exc:
        log.warning("drafter: ExtractionError for %r (run_id=%s): %s", scored.company, run_id, exc)
        return None
