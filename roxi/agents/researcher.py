from __future__ import annotations

import hashlib
import logging
import time

import anthropic

from roxi.config import VerticalConfig
from roxi.llm import ExtractionError, _get_client, structured
from roxi.models import ResearchBrief, ScoredSignal
from roxi import store

log = logging.getLogger(__name__)

_SEARCH_SYSTEM = """\
You are researching a B2B prospect for a sales team. You have web search available. \
Use it to find information a salesperson would want before a first call. \
Run 2–3 targeted searches. Take notes on what you find. \
Be factual — only record what you can verify from search results. \
Do not invent details. If you find nothing substantial, say so clearly.

Focus on:
- Company website and basic profile
- Fleet size or number of trucks (if public)
- Operating lanes and cross-border activity
- Any software or TMS they mention using
- Who the decision-maker likely is (title only, not name)
- Any news, job postings, or signals that add context

Product context: {product_brief}
"""

_EXTRACT_SYSTEM = """\
You have research notes about a company. Extract a structured brief from the notes. \
Only include facts that appeared in the notes — do not add anything. \
If the notes are thin, return confidence=low and fewer hooks rather than padding. \
hooks should be specific, verifiable facts a salesperson can reference in an email opener.
"""

from roxi.llm import COST_PER_MILLION as _COST_PER_MILLION


def research_company(scored: ScoredSignal, vertical: VerticalConfig, run_id: str | None = None) -> ResearchBrief | None:
    client = _get_client()

    search_user = (
        f"Research this company for a sales call:\n"
        f"Company: {scored.company}\n"
        f"Location: {scored.location}\n"
        f"Signal: {scored.signal_type} — {scored.evidence}\n\n"
        f"Find fleet size, operating lanes, current software stack, and decision-maker title."
    )

    _prompt_version = hashlib.sha256(_SEARCH_SYSTEM.encode()).hexdigest()[:16]
    _input_hash = hashlib.sha256(search_user.encode()).hexdigest()[:16]

    try:
        t0 = time.perf_counter()
        search_response = client.messages.create(
            model=vertical.models.researcher,
            max_tokens=2000,
            system=_SEARCH_SYSTEM.format(product_brief=vertical.product_brief),
            messages=[{"role": "user", "content": search_user}],
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
    except anthropic.APIError as exc:
        log.error("researcher: web search APIError for %r (run_id=%s): %s", scored.company, run_id, exc)
        return None

    # Track cost for the search call (not via structured() since it uses web search tool)
    input_tok = search_response.usage.input_tokens
    output_tok = search_response.usage.output_tokens
    rates = _COST_PER_MILLION.get(vertical.models.researcher, {"input": 0, "output": 0})
    cost_usd = (input_tok * rates["input"] + output_tok * rates["output"]) / 1_000_000
    has_text = any(hasattr(b, "text") for b in search_response.content)
    try:
        store.log_llm_call(
            model=vertical.models.researcher,
            agent="researcher/search",
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            lead_id=None,
            run_id=run_id,
            prompt_version=_prompt_version,
            input_hash=_input_hash,
            outcome="ok" if has_text else "empty",
        )
    except Exception as exc:
        log.debug("researcher: failed to log search call: %s", exc)

    notes = "\n\n".join(
        block.text
        for block in search_response.content
        if hasattr(block, "text")
    )
    if not notes.strip():
        log.info("researcher: no search results for %r (run_id=%s)", scored.company, run_id)
        return None

    try:
        brief = structured(
            model=vertical.models.researcher,
            system=_EXTRACT_SYSTEM,
            user=f"Research notes:\n{notes}\n\nExtract the ResearchBrief.",
            schema=ResearchBrief,
            agent="researcher",
            run_id=run_id,
        )
    except ExtractionError as exc:
        log.warning("researcher: ExtractionError extracting brief for %r (run_id=%s): %s", scored.company, run_id, exc)
        return None

    log.info("researcher: brief for %r — confidence=%s hooks=%d (run_id=%s)",
             scored.company, brief.confidence, len(brief.hooks), run_id)
    return brief
