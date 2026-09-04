from __future__ import annotations

import logging

from roxi.config import VerticalConfig
from roxi.llm import ExtractionError, structured
from roxi.models import RawItem, Signal

log = logging.getLogger(__name__)

_SYSTEM = """\
You are the Extractor for a B2B lead pipeline. Your job is to read one raw item \
(a job posting, regulatory filing, or forum post) and pull out structured facts. \
You read literally. You make no judgment about whether the company is worth contacting.

Rules:
- Extract company name and fleet size ONLY when explicitly stated or directly implied by the text.
  Do not guess fleet size from company tone, job title count, or industry cues.
- evidence MUST be a verbatim sentence or phrase copied word-for-word from the source.
  Never paraphrase. If no single sentence captures it, quote the most relevant fragment.
- Classify poster_role from how the person writes:
    "my dispatcher", "our dispatcher" → the poster has employees → "decision_maker"
    "my company", "my boss", "they make me" → poster is subordinate → "driver"
    Not a first-person post (job ad, filing) → infer from context or use "unknown"
    Job posting placed by a company → "decision_maker" (the employer is the poster)
- signal_type: "hiring" for job postings and recruiting signals,
  "authority_grant" for regulatory filings and authority approvals,
  "pain_complaint" for forum posts expressing frustration with paperwork or software.
- Set is_company_identifiable to false if no specific named company can be determined
  (e.g. generic forum rant with no company name anywhere).
- ICP context: {icp_description}
"""


def extract(raw: RawItem, vertical: VerticalConfig, run_id: str | None = None) -> Signal | None:
    system = _SYSTEM.format(icp_description=vertical.icp.description)
    if len(raw.body) > 6000:
        log.debug("extractor: truncating body from %d chars (channel=%s)", len(raw.body), raw.channel)
    body_preview = raw.body[:6000]
    user = f"""\
Channel: {raw.channel}
Title: {raw.title}
Body:
{body_preview}

Extract the Signal from this item."""

    try:
        signal = structured(
            model=vertical.models.extractor,
            system=system,
            user=user,
            schema=Signal,
            agent="extractor",
            run_id=run_id,
        )
    except ExtractionError as exc:
        log.warning("extractor: ExtractionError for %r (channel=%s): %s", raw.title[:80], raw.channel, exc)
        return None

    if not signal.is_company_identifiable:
        log.debug("extractor: no identifiable company in %r — dropped", raw.title[:80])
        return None

    return signal
