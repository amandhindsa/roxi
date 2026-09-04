"""
Phase 8 — content pipeline data model.

Text → approve output.
Video → approve Director's brief before any generation spend fires.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class BrandBrief(BaseModel):
    vertical_id: str
    brand_name: str
    brand_voice: str
    topics: list[str]
    platforms: list[str]
    prohibited_claims: list[str] = []


class ContentPlan(BaseModel):
    week_of: str
    items: list["ContentItem"]


class ContentItem(BaseModel):
    id: str
    platform: str
    media_type: Literal["text", "image", "video"]
    topic: str
    angle: str
    status: Literal["planned", "directing", "pending_approval", "approved", "generating", "reviewing", "publishing", "done", "rejected"] = "planned"


class DirectorBrief(BaseModel):
    item_id: str
    media_type: Literal["text", "image", "video"]
    platform: str
    copy: str | None = None
    image_prompt: str | None = None
    video_script: str | None = None
    shot_list: list[str] = []
    voice_style: str | None = None
    duration_seconds: int | None = None
    estimated_cost_usd: float | None = None


class GeneratedAsset(BaseModel):
    item_id: str
    media_type: Literal["text", "image", "video"]
    url: str | None = None
    text_content: str | None = None
    generation_cost_usd: float = 0.0
    provider: str = ""


class ReviewResult(BaseModel):
    item_id: str
    approved: bool
    issues: list[str]
    brand_compliant: bool
    claims_substantiated: bool
    reviewer_notes: str


class PublishResult(BaseModel):
    item_id: str
    platform: str
    success: bool
    post_url: str | None = None
    error: str | None = None
