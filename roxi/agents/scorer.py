from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from roxi.config import VerticalConfig
from roxi.llm import ExtractionError, structured
from roxi.models import RuleFired, Signal, ScoredSignal

log = logging.getLogger(__name__)

_SYSTEM = """\
You are the Scorer for a B2B lead pipeline. You apply a stated rule set to a clean signal \
and return a numeric score with its arithmetic shown. You are the skeptic: you do not \
consider whether a lead could be made to sound appealing. You apply only what the evidence supports.

Scoring procedure:
1. Check every disqualifier first. If any fires, set score=0 and disqualified_by to the rule name.
   Stop — do not score further.
2. Start from 0. Apply each additive rule in the list. For each rule that fires, record it in
   rules_fired with its exact delta. Sum the deltas for the final score. Cap at 100.
3. Only fire a rule if the signal's fields directly support it. Do not infer or assume.
4. reasoning is for the internal log — be precise and cite which fields you used.
   Do NOT write why_now or any sales-facing prose here.

Rules:
{rules_block}

Disqualifiers (fire any one of these → immediate disqualification):
{disqualifiers_block}
"""


def _build_rules_block(vertical: VerticalConfig) -> tuple[str, str]:
    additive = []
    disqualifiers = []
    for r in vertical.scoring_rules:
        if r.delta == "disqualify":
            disqualifiers.append(f"- {r.rule}")
        else:
            additive.append(f"- {r.rule}: +{r.delta}")
    return "\n".join(additive), "\n".join(disqualifiers)


class _ScorerOutput(BaseModel):
    score: int
    rules_fired: list[RuleFired]
    reasoning: str
    disqualified_by: str | None = None


def score(signal: Signal, vertical: VerticalConfig, run_id: str | None = None) -> ScoredSignal | None:
    additive_block, disq_block = _build_rules_block(vertical)
    system = _SYSTEM.format(
        rules_block=additive_block,
        disqualifiers_block=disq_block,
    )

    signal_summary = json.dumps({
        "company": signal.company,
        "location": signal.location,
        "fleet_size": signal.fleet_size,
        "signal_type": signal.signal_type,
        "signal_date": str(signal.signal_date) if signal.signal_date else None,
        "evidence": signal.evidence,
        "poster_role": signal.poster_role,
    }, indent=2)

    user = f"Score this signal:\n{signal_summary}"

    try:
        out = structured(
            model=vertical.models.scorer,
            system=system,
            user=user,
            schema=_ScorerOutput,
            agent="scorer",
            run_id=run_id,
        )
    except ExtractionError as exc:
        log.warning("scorer: ExtractionError for %r (run_id=%s): %s — signal will not enter dedup",
                    signal.company, run_id, exc)
        return None

    scored = ScoredSignal(
        **signal.model_dump(),
        score=max(0, min(100, out.score)),
        rules_fired=out.rules_fired,
        reasoning=out.reasoning,
        disqualified_by=out.disqualified_by,
    )

    if scored.disqualified_by:
        log.info("scorer: %r disqualified by %r (run_id=%s)", signal.company, scored.disqualified_by, run_id)
    else:
        log.info("scorer: %r → score=%d (run_id=%s)", signal.company, scored.score, run_id)

    return scored
