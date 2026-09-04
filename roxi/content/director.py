"""
Phase 8 — Director agent.

Writes the production brief for one ContentItem. For video, this brief is
approved by a human BEFORE any generation spend fires. For text and image,
the output itself is approved.
"""

from __future__ import annotations

import logging

from roxi.content.models import BrandBrief, ContentItem, DirectorBrief
from roxi.llm import SONNET, ExtractionError, structured

log = logging.getLogger(__name__)

_SYSTEM = """\
You are the Director for a B2B content operation. Given an approved content item and brand brief, \
you write the production brief.

For TEXT: write the post copy, ready to publish. Stay in brand voice. No filler.
For IMAGE: write a detailed image generation prompt. Be specific about style, subject, composition.
For VIDEO: write a script and shot list. Keep under 90 seconds. Include voice style and duration. \
  This is the brief a human approves BEFORE generation — make it clear and editable.

Brand voice must match the brief exactly. Do not invent claims not in the brief.
"""


def direct(
    item: ContentItem,
    brand_brief: BrandBrief,
    run_id: str | None = None,
) -> DirectorBrief | None:
    user = (
        f"Content item:\n"
        f"  Platform: {item.platform}\n"
        f"  Media type: {item.media_type}\n"
        f"  Topic: {item.topic}\n"
        f"  Angle: {item.angle}\n\n"
        f"Brand brief:\n{brand_brief.model_dump_json(indent=2)}\n\n"
        f"Write the production brief."
    )

    try:
        return structured(
            model=SONNET,
            system=_SYSTEM,
            user=user,
            schema=DirectorBrief,
            agent="director",
            run_id=run_id,
        )
    except ExtractionError as exc:
        log.warning("director: ExtractionError for item %s platform=%s media_type=%s: %s",
                    item.id, item.platform, item.media_type, exc)
        return None
