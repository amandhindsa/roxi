"""
Phase 8 — Reviewer agent.

Skeptic. Checks a generated asset against brand rules and claim substantiation.
The Director wants the asset to be compelling; the Reviewer asks whether the claims
are supportable and whether it matches brand rules. Opposite dispositions — different calls.

The Reviewer is an automatic pre-screen, never the final approver.
"""

from __future__ import annotations

import logging

from roxi.content.models import BrandBrief, GeneratedAsset, ReviewResult
from roxi.llm import SONNET, ExtractionError, structured

log = logging.getLogger(__name__)

_SYSTEM = """\
You are the Reviewer for a B2B content operation. You review a generated asset \
against the brand brief. You are a skeptic — your job is to find problems, not to \
approve things.

Check:
1. Brand compliance — does it match brand voice? Does it avoid prohibited claims?
2. Claim substantiation — can every factual claim in the copy be verified from the brief?
   Flag unverifiable claims, especially numbers and superlatives.
3. Platform fit — is the format and length appropriate for the platform?
4. Nothing that would embarrass the brand in a screenshot.

If you find no issues, say so plainly. Do not invent problems to seem thorough.
"""


def review(
    asset: GeneratedAsset,
    brief: BrandBrief,
    run_id: str | None = None,
) -> ReviewResult | None:
    content = asset.text_content or asset.url or "(no content)"
    user = (
        f"Asset to review:\n"
        f"  Media type: {asset.media_type}\n"
        f"  Content: {content[:3000]}\n\n"
        f"Brand brief:\n{brief.model_dump_json(indent=2)}\n\n"
        f"Review the asset against the brand brief."
    )

    try:
        return structured(
            model=SONNET,
            system=_SYSTEM,
            user=user,
            schema=ReviewResult,
            agent="reviewer",
            run_id=run_id,
        )
    except ExtractionError as exc:
        log.error("reviewer: ExtractionError for item %s media_type=%s: %s — asset may publish unreviewed",
                  asset.item_id, asset.media_type, exc)
        return None
