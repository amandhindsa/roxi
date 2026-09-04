from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class RawItem(BaseModel):
    channel: Literal["job_boards", "registry", "reddit"]
    source_url: str
    fetched_at: datetime
    title: str
    body: str


class Signal(BaseModel):
    company: str
    company_domain: Optional[str] = None
    location: Optional[str] = None
    fleet_size: Optional[int] = None
    signal_type: Literal["hiring", "authority_grant", "pain_complaint"]
    signal_date: Optional[date] = None
    evidence: str
    poster_role: Literal["decision_maker", "driver", "unknown"]
    is_company_identifiable: bool

    @field_validator("evidence")
    @classmethod
    def evidence_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("evidence must be a non-empty verbatim sentence from the source")
        return v


class RuleFired(BaseModel):
    rule: str
    delta: int


class ScoredSignal(Signal):
    score: int
    rules_fired: list[RuleFired]
    reasoning: str
    disqualified_by: Optional[str] = None


class ResearchBrief(BaseModel):
    company_summary: str
    fleet_estimate: Optional[str] = None
    operating_lanes: list[str] = []
    current_stack_guess: Optional[str] = None
    decision_maker_title: Optional[str] = None
    hooks: list[str] = []
    confidence: Literal["high", "medium", "low"]


class EmailDraft(BaseModel):
    why_now: str
    subject: str
    body: str
    hook_used: str


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    raw: RawItem
    # signal holds the pre-scoring Signal; scored is the full ScoredSignal after scoring
    signal: Signal
    scored: ScoredSignal
    research: Optional[ResearchBrief] = None
    draft: Optional[EmailDraft] = None
    dedupe_key: str
    status: Literal["pending", "approved", "rejected", "sent", "replied"] = "pending"
    contact_email: Optional[str] = None  # verified address; set by reviewer at approval — never fabricated
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Multi-tenancy fields
    org_id: Optional[str] = None
    subscription_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    draft_edited: bool = False


class Organisation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str  # URL-safe identifier
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Member(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    org_id: str
    user_id: str  # Supabase auth user UUID
    email: str
    role: Literal["owner", "reviewer", "viewer"]
    invited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    joined_at: Optional[datetime] = None


class Subscription(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    org_id: str
    vertical_id: str
    rules_version_id: Optional[str] = None  # None = use file-based rules
    status: Literal["active", "paused", "cancelled"] = "active"
    paused: bool = False
    daily_research_budget: int = 15
    spend_ceiling_usd: float = 5.0
    qualify_threshold: int = 70
    delivery_hour: int = 8  # 0-23
    delivery_timezone: str = "America/Toronto"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VerticalRules(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    subscription_id: str
    version: int
    rules_json: str   # JSON-encoded list of scoring rules
    icp_json: str     # JSON-encoded ICP config
    product_brief: str
    summary: str      # plain-English summary
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SetupMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SetupSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    org_id: str
    subscription_id: Optional[str] = None
    state: Literal["active", "complete", "abandoned"] = "active"
    messages: list[SetupMessage] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LeadFeedback(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lead_id: str
    reason: Literal["wrong_size", "wrong_industry", "existing_customer", "bad_timing", "other"]
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceHealth(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    subscription_id: str
    source_name: str
    last_run_at: Optional[datetime] = None
    last_count: int = 0
    consecutive_empty: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
