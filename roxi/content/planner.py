"""
Phase 8 — Planner agent.

Decides what to say this week per platform, from the brand brief and source material.
Output is a ContentPlan: a set of ContentItems with topic, angle, and platform.
Human approves the plan before the Director writes any briefs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from roxi.content.models import BrandBrief, ContentItem, ContentPlan
from roxi.llm import SONNET, ExtractionError, structured

log = logging.getLogger(__name__)

_SYSTEM = """\
You are the Planner for a B2B content operation. Given a brand brief and recent source material \
(blog posts, product updates, customer stories), you decide what content to produce this week \
and on which platforms.

Rules:
- Propose only platforms listed in the brand brief.
- Each item must have a specific topic and angle — not "post about our product" but \
  "how Canadian carriers calculate the ROI of automating eManifest paperwork".
- Text and image posts for this week. Video only if there is genuine source material for it.
- Never propose auto-posting to Reddit or LinkedIn — those require human review and manual posting.
- Quantity: 3–7 items per week. More is not better.
"""


def plan_week(
    brand_brief: BrandBrief,
    source_material: str,
    week_of: date | None = None,
    run_id: str | None = None,
) -> ContentPlan | None:
    from pydantic import BaseModel

    class _Plan(BaseModel):
        items: list[dict]

    week_str = str(week_of or date.today())
    user = (
        f"Brand brief:\n{brand_brief.model_dump_json(indent=2)}\n\n"
        f"Source material for this week:\n{source_material[:4000]}\n\n"
        f"Week of: {week_str}\n\nPropose the content plan."
    )

    try:
        result = structured(
            model=SONNET,
            system=_SYSTEM,
            user=user,
            schema=_Plan,
            agent="planner",
            run_id=run_id,
        )
    except ExtractionError as exc:
        log.warning("planner: ExtractionError for %s week=%s: %s", brand_brief.vertical_id, week_str, exc)
        return None

    items = []
    for item_data in result.items:
        items.append(ContentItem(
            id=str(uuid.uuid4()),
            platform=item_data.get("platform", ""),
            media_type=item_data.get("media_type", "text"),
            topic=item_data.get("topic", ""),
            angle=item_data.get("angle", ""),
        ))

    plan = ContentPlan(week_of=week_str, items=items)
    log.info("planner: %d items for %s week=%s", len(items), brand_brief.vertical_id, week_str)
    return plan
