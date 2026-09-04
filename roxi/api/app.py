"""
Roxi API server — multi-tenant edition with Supabase Auth JWT verification.

Endpoints (existing):
  POST /whatsapp/webhook       — Twilio WhatsApp webhook (approve/reject via reply)
  GET  /api/leads              — List leads with filters (+ optional subscription_id)
  GET  /api/leads/{id}         — Single lead
  PATCH /api/leads/{id}        — Update lead status / rejection_reason / draft_edited_json
  GET  /api/stats              — Funnel + cost stats (+ optional subscription_id)
  GET  /api/runs               — Pipeline run history
  GET  /api/runs/{id}          — Single run detail + LLM call breakdown
  GET  /api/telemetry/events   — Structured event log
  GET  /api/telemetry/costs    — Daily cost series
  GET  /api/suppression        — Suppression list entries
  DELETE /api/suppression      — Remove an entry (requires ROXI_API_KEY)
  GET  /healthz                — Liveness probe (process alive)
  GET  /readyz                 — Readiness probe (DB + required env vars)
  GET  /health                 — Deep health check (DB, env vars, Twilio)

New endpoints:
  POST   /api/orgs                                  — create org (JWT)
  GET    /api/orgs/me                               — current user's org (JWT)
  GET    /api/orgs/{org_id}/members                 — list members (JWT)
  POST   /api/orgs/{org_id}/members/invite          — invite by email (JWT, owner)
  DELETE /api/orgs/{org_id}/members/{user_id}       — remove member (JWT, owner)
  PATCH  /api/orgs/{org_id}/members/{user_id}       — change role (JWT, owner)
  GET    /api/subscriptions                         — list subscriptions (JWT)
  POST   /api/subscriptions                         — create subscription (JWT)
  GET    /api/subscriptions/{id}                    — get subscription (JWT)
  PATCH  /api/subscriptions/{id}                    — update subscription (JWT)
  GET    /api/subscriptions/{id}/rules              — list rule versions (JWT)
  GET    /api/subscriptions/{id}/rules/latest       — latest rule version (JWT)
  POST   /api/subscriptions/{id}/rules              — save new rule version (JWT)
  GET    /api/rules/{rule_id}/preview               — preview rules against recent leads (JWT)
  POST   /api/setup/sessions                        — start setup interview session (JWT)
  GET    /api/setup/sessions/{id}                   — get setup session (JWT)
  POST   /api/setup/sessions/{id}/message           — advance session with AI (JWT)
  GET    /api/subscriptions/{id}/sources            — source health (JWT)
  GET    /api/subscriptions/{id}/scheduled-runs     — scheduled runs (JWT)
  POST   /api/leads/{id}/feedback                   — add rejection feedback (JWT)
  GET    /api/leads/{id}/feedback                   — list feedback (JWT)
  GET    /api/subscriptions/{id}/results            — reply rates + rejection analysis (JWT)
  GET    /api/operator/orgs                         — all orgs with stats (operator key)
  GET    /api/operator/source-health                — quiet sources (operator key)
  GET    /api/operator/costs                        — per-org cost breakdown (operator key)
  GET    /api/operator/runs                         — recent runs (operator key)
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
import urllib.parse
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

try:
    import jwt  # PyJWT
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

from contextlib import asynccontextmanager

from roxi import store
from roxi.models import Lead

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    store.init_db()
    # Start the daily pipeline scheduler
    try:
        from roxi.scheduler import start_scheduler, stop_scheduler
        start_scheduler(store)
        log.info("Scheduler started")
        yield
        stop_scheduler()
        log.info("Scheduler stopped")
    except ImportError:
        log.warning("APScheduler not installed — scheduler disabled. Run: pip install apscheduler")
        yield
    except Exception as exc:
        log.error("Scheduler startup failed: %s", exc, exc_info=True)
        yield


app = FastAPI(title="Roxi API", version="0.4.0", lifespan=_lifespan)

_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ROXI_CORS_ORIGINS", "http://localhost:3000").split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

_bearer = HTTPBearer(auto_error=False)

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


# ── Request logging middleware ────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    log.info(
        "http %s %s %d %dms",
        request.method, request.url.path, response.status_code, latency_ms,
    )
    return response


# ── Rate limiting (slowapi) ───────────────────────────────────────────────────

limiter = None
_RATE_LIMIT = False
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _RATE_LIMIT = True
except ImportError:
    log.warning("slowapi not installed — rate limiting disabled. Run: pip install slowapi")


def _rate_limit(limit_string: str):
    """Decorator factory; no-op if slowapi is not installed."""
    if _RATE_LIMIT:
        return limiter.limit(limit_string)
    def noop(fn):
        return fn
    return noop


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _decode_jwt(token: str) -> dict | None:
    if not _JWT_AVAILABLE:
        log.warning("PyJWT not installed — JWT verification disabled")
        return None
    if not SUPABASE_JWT_SECRET:
        log.warning("SUPABASE_JWT_SECRET not set — JWT verification disabled")
        return None
    try:
        return jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except Exception:
        return None


def _get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    if not credentials:
        return None
    return _decode_jwt(credentials.credentials)


def _require_auth(user: dict | None = Depends(_get_current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    api_key = os.environ.get("ROXI_API_KEY")
    if not api_key:
        return  # auth disabled in dev when ROXI_API_KEY is not set
    token = (credentials.credentials if credentials else None) or x_api_key
    if not token or not hmac.compare_digest(token, api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_operator(
    x_operator_key: str | None = Header(None, alias="X-Operator-Key"),
) -> None:
    key = os.environ.get("OPERATOR_API_KEY")
    if not key or not x_operator_key or not hmac.compare_digest(x_operator_key, key):
        raise HTTPException(status_code=401, detail="Operator access required")


def _call_store(fn_name: str, *args, **kwargs) -> Any:
    """
    Call a store function by name. Returns 501 if the function doesn't exist yet,
    allowing graceful degradation while store functions are being added.
    """
    fn = getattr(store, fn_name, None)
    if fn is None:
        raise HTTPException(status_code=501, detail=f"store.{fn_name} not implemented yet")
    return fn(*args, **kwargs)


# ── WhatsApp webhook (Twilio) ─────────────────────────────────────────────────

def _verify_twilio_signature(body: bytes, url: str, signature: str | None) -> bool:
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        log.error("TWILIO_AUTH_TOKEN not set — rejecting all /whatsapp/webhook requests")
        return False
    if not signature:
        return False
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        params = dict(urllib.parse.parse_qsl(body.decode()))
        return validator.validate(url, params, signature)
    except Exception as exc:
        log.warning("Twilio signature validation error: %s", exc)
        return False


@app.post("/whatsapp/webhook")
@_rate_limit("30/minute")
async def whatsapp_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Twilio-Signature")
    url = str(request.url)
    if not _verify_twilio_signature(body, url, signature):
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")

    params = dict(urllib.parse.parse_qsl(body.decode()))
    text = params.get("Body", "").strip().lower()

    # Expected format: "approve <8-char-id>" or "reject <8-char-id>"
    parts = text.split()
    if len(parts) != 2 or parts[0] not in ("approve", "reject"):
        return Response(
            content='<?xml version="1.0"?><Response><Message>Reply "approve &lt;id&gt;" or "reject &lt;id&gt;".</Message></Response>',
            media_type="application/xml",
        )

    decision = "approved" if parts[0] == "approve" else "rejected"
    short_id = parts[1]

    lead = store.find_lead_by_short_id(short_id)
    if not lead:
        return Response(
            content=f'<?xml version="1.0"?><Response><Message>Lead "{short_id}" not found.</Message></Response>',
            media_type="application/xml",
        )

    try:
        store.update_status(lead["id"], decision)
        log.info("Lead %s → %s via WhatsApp", lead["id"], decision)
    except Exception as exc:
        log.error("Failed to update lead %s: %s", lead["id"], exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error updating lead status")

    company = json.loads(lead.get("scored_json", "{}")).get("company", lead["id"])
    return Response(
        content=f'<?xml version="1.0"?><Response><Message>✅ {company} marked {decision}.</Message></Response>',
        media_type="application/xml",
    )


# ── Leads ────────────────────────────────────────────────────────────────────

@app.get("/api/leads")
@_rate_limit("120/minute")
async def list_leads(
    request: Request,
    vertical: str = "hauler_ai",
    status: str = "pending",
    limit: int = Query(50, le=200),
    offset: int = 0,
    subscription_id: str | None = None,
):
    fn = getattr(store, "list_leads", None)
    if fn is None:
        raise HTTPException(status_code=501, detail="store.list_leads not implemented yet")
    # Pass subscription_id only if the store function supports it
    import inspect
    sig = inspect.signature(fn)
    if "subscription_id" in sig.parameters:
        return fn(
            vertical_id=vertical,
            status=status,
            limit=limit,
            offset=offset,
            subscription_id=subscription_id,
        )
    return fn(vertical_id=vertical, status=status, limit=limit, offset=offset)


@app.get("/api/leads/{lead_id}")
async def get_lead(lead_id: str):
    row = store.get_lead(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row


class StatusUpdate(BaseModel):
    status: str
    rejection_reason: str | None = None
    draft_edited_json: dict | None = None


@app.patch("/api/leads/{lead_id}")
async def update_lead_status(
    lead_id: str,
    body: StatusUpdate,
    _auth=Depends(_require_api_key),
):
    allowed = {"approved", "rejected", "sent", "replied"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    row = store.get_lead(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    store.update_status(lead_id, body.status)

    # Optional extended fields — call store helpers if available
    if body.rejection_reason is not None:
        fn = getattr(store, "update_lead_rejection_reason", None)
        if fn:
            fn(lead_id, body.rejection_reason)

    if body.draft_edited_json is not None:
        fn = getattr(store, "update_lead_draft_edited", None)
        if fn:
            fn(lead_id, body.draft_edited_json)

    log.info("Lead %s → %s via API", lead_id, body.status)
    return {"id": lead_id, "status": body.status}


# ── Stats ────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats(
    vertical: str = "hauler_ai",
    days: int = 30,
    subscription_id: str | None = None,
):
    fn = getattr(store, "get_stats", None)
    if fn is None:
        raise HTTPException(status_code=501, detail="store.get_stats not implemented yet")
    import inspect
    sig = inspect.signature(fn)
    if "subscription_id" in sig.parameters:
        return fn(vertical_id=vertical, days=days, subscription_id=subscription_id)
    return fn(vertical_id=vertical, days=days)


# ── Runs ─────────────────────────────────────────────────────────────────────

@app.get("/api/runs")
async def list_runs(vertical: str | None = None, limit: int = Query(20, le=100)):
    return store.list_runs(vertical_id=vertical, limit=limit)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    calls = store.list_llm_calls(run_id=run_id)
    return {"run": run, "llm_calls": calls}


# ── Telemetry ────────────────────────────────────────────────────────────────

@app.get("/api/telemetry/events")
async def telemetry_events(
    run_id: str | None = None,
    agent: str | None = None,
    vertical_id: str | None = None,
    limit: int = Query(100, le=500),
):
    return store.list_events(run_id=run_id, agent=agent, vertical_id=vertical_id, limit=limit)


@app.get("/api/telemetry/costs")
async def telemetry_costs(days: int = 30, vertical: str | None = None):
    return store.daily_costs(days=days, vertical_id=vertical)


# ── Suppression ──────────────────────────────────────────────────────────────

@app.get("/api/suppression")
async def list_suppression(channel: str | None = None, limit: int = Query(100, le=500)):
    return store.list_suppression(channel=channel, limit=limit)


class SuppressionRemove(BaseModel):
    contact_identifier: str
    channel: str


@app.delete("/api/suppression")
async def remove_suppression(body: SuppressionRemove, _auth=Depends(_require_api_key)):
    removed = store.remove_from_suppression_list(
        contact_identifier=body.contact_identifier,
        channel=body.channel,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Entry not found in suppression list")
    log.info("Removed suppression: %s on %s", body.contact_identifier, body.channel)
    return {"removed": True}


# ── Health probes ─────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz():
    """Liveness probe — confirms the process is alive. Never blocks."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """
    Readiness probe — confirms the service can handle traffic.
    Returns 503 if DB is unreachable or ANTHROPIC_API_KEY is missing.
    """
    issues: list[str] = []

    try:
        with store._conn() as con:
            con.execute("SELECT 1").fetchone()
    except Exception as exc:
        issues.append(f"db: {exc}")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        issues.append("ANTHROPIC_API_KEY not set")

    if issues:
        return JSONResponse(status_code=503, content={"status": "not_ready", "issues": issues})
    return {"status": "ready"}


@app.get("/health")
async def health():
    """Deep health check — includes optional integrations and latency."""
    checks: dict[str, dict] = {}
    overall = "ok"

    # DB connectivity
    try:
        t0 = time.perf_counter()
        with store._conn() as con:
            con.execute("SELECT 1").fetchone()
        checks["db"] = {"status": "ok", "latency_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        checks["db"] = {"status": "error", "error": str(exc)}
        overall = "degraded"

    required_vars = ["ANTHROPIC_API_KEY"]
    optional_vars = [
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
        "TWILIO_WHATSAPP_FROM", "WHATSAPP_TO",
        "INSTANTLY_API_KEY", "INSTANTLY_CAMPAIGN_ID",
        "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
        "ROXI_API_KEY", "SUPABASE_JWT_SECRET",
    ]

    env_status: dict = {}
    for var in required_vars:
        present = bool(os.environ.get(var))
        env_status[var] = "present" if present else "MISSING"
        if not present:
            overall = "degraded"
    for var in optional_vars:
        env_status[var] = "present" if os.environ.get(var) else "absent"

    checks["env"] = {"status": "ok" if overall == "ok" else "degraded", "vars": env_status}

    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if twilio_sid and twilio_token:
        try:
            import anyio
            import requests as _req

            def _ping_twilio() -> dict:
                t0 = time.perf_counter()
                r = _req.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}.json",
                    auth=(twilio_sid, twilio_token),
                    timeout=5,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                return {
                    "status": "ok" if r.status_code == 200 else "error",
                    "http_status": r.status_code,
                    "latency_ms": latency_ms,
                }

            checks["twilio"] = await anyio.to_thread.run_sync(_ping_twilio)
        except Exception as exc:
            checks["twilio"] = {"status": "error", "error": str(exc)}
    else:
        checks["twilio"] = {"status": "not_configured"}

    return {"status": overall, "checks": checks}


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Organisations
# ═══════════════════════════════════════════════════════════════════════════════

class OrgCreate(BaseModel):
    name: str
    slug: str | None = None


@app.post("/api/orgs", status_code=201)
async def create_org(body: OrgCreate, user: dict = Depends(_require_auth)):
    return _call_store("create_org", name=body.name, slug=body.slug, owner_id=user["sub"])


@app.get("/api/orgs/me")
async def get_my_org(user: dict = Depends(_require_auth)):
    result = _call_store("get_org_for_user", user_id=user["sub"])
    if not result:
        raise HTTPException(status_code=404, detail="No org found for current user")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Members
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/orgs/{org_id}/members")
async def list_members(org_id: str, user: dict = Depends(_require_auth)):
    return _call_store("list_org_members", org_id=org_id, requesting_user_id=user["sub"])


class InviteMember(BaseModel):
    email: str
    role: str = "reviewer"


@app.post("/api/orgs/{org_id}/members/invite", status_code=201)
async def invite_member(org_id: str, body: InviteMember, user: dict = Depends(_require_auth)):
    return _call_store(
        "invite_org_member",
        org_id=org_id,
        email=body.email,
        role=body.role,
        requesting_user_id=user["sub"],
    )


@app.delete("/api/orgs/{org_id}/members/{member_user_id}")
async def remove_member(
    org_id: str,
    member_user_id: str,
    user: dict = Depends(_require_auth),
):
    return _call_store(
        "remove_org_member",
        org_id=org_id,
        member_user_id=member_user_id,
        requesting_user_id=user["sub"],
    )


class RoleUpdate(BaseModel):
    role: str


@app.patch("/api/orgs/{org_id}/members/{member_user_id}")
async def update_member_role(
    org_id: str,
    member_user_id: str,
    body: RoleUpdate,
    user: dict = Depends(_require_auth),
):
    return _call_store(
        "update_org_member_role",
        org_id=org_id,
        member_user_id=member_user_id,
        role=body.role,
        requesting_user_id=user["sub"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Subscriptions
# ═══════════════════════════════════════════════════════════════════════════════

class SubscriptionCreate(BaseModel):
    vertical_id: str
    name: str | None = None
    delivery_hour: int | None = None
    budget_usd: float | None = None
    paused: bool = False
    config: dict | None = None


class SubscriptionUpdate(BaseModel):
    name: str | None = None
    paused: bool | None = None
    delivery_hour: int | None = None
    budget_usd: float | None = None
    config: dict | None = None


@app.get("/api/subscriptions")
async def list_subscriptions(user: dict = Depends(_require_auth)):
    return _call_store("list_subscriptions_for_user", user_id=user["sub"])


@app.post("/api/subscriptions", status_code=201)
async def create_subscription(body: SubscriptionCreate, user: dict = Depends(_require_auth)):
    return _call_store(
        "create_subscription",
        user_id=user["sub"],
        vertical_id=body.vertical_id,
        name=body.name,
        delivery_hour=body.delivery_hour,
        budget_usd=body.budget_usd,
        paused=body.paused,
        config=body.config,
    )


@app.get("/api/subscriptions/{subscription_id}")
async def get_subscription(subscription_id: str, user: dict = Depends(_require_auth)):
    result = _call_store(
        "get_subscription",
        subscription_id=subscription_id,
        user_id=user["sub"],
    )
    if not result:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return result


@app.patch("/api/subscriptions/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    body: SubscriptionUpdate,
    user: dict = Depends(_require_auth),
):
    return _call_store(
        "update_subscription",
        subscription_id=subscription_id,
        user_id=user["sub"],
        **{k: v for k, v in body.model_dump().items() if v is not None},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Vertical rules
# ═══════════════════════════════════════════════════════════════════════════════

class RulesCreate(BaseModel):
    rules: dict
    notes: str | None = None


@app.get("/api/subscriptions/{subscription_id}/rules")
async def list_rule_versions(subscription_id: str, user: dict = Depends(_require_auth)):
    return _call_store(
        "list_rule_versions",
        subscription_id=subscription_id,
        user_id=user["sub"],
    )


@app.get("/api/subscriptions/{subscription_id}/rules/latest")
async def get_latest_rules(subscription_id: str, user: dict = Depends(_require_auth)):
    result = _call_store(
        "get_latest_rules",
        subscription_id=subscription_id,
        user_id=user["sub"],
    )
    if not result:
        raise HTTPException(status_code=404, detail="No rules found for subscription")
    return result


@app.post("/api/subscriptions/{subscription_id}/rules", status_code=201)
async def save_rules(
    subscription_id: str,
    body: RulesCreate,
    user: dict = Depends(_require_auth),
):
    return _call_store(
        "save_rule_version",
        subscription_id=subscription_id,
        user_id=user["sub"],
        rules=body.rules,
        notes=body.notes,
    )


class RulesPreviewRequest(BaseModel):
    rules: dict
    days: int = 7


@app.get("/api/rules/{rule_id}/preview")
async def preview_rules(rule_id: str, user: dict = Depends(_require_auth)):
    """
    Preview: apply saved rule version against recent leads.
    Read-only simulation — no DB writes.
    """
    rule_version = _call_store("get_rule_version", rule_id=rule_id, user_id=user["sub"])
    if not rule_version:
        raise HTTPException(status_code=404, detail="Rule version not found")
    subscription_id = rule_version.get("subscription_id")
    recent_leads = _call_store(
        "list_leads_for_preview",
        subscription_id=subscription_id,
        days=7,
        user_id=user["sub"],
    )
    return _call_store(
        "simulate_rules",
        rules=rule_version["rules"],
        leads=recent_leads,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Setup interview
# ═══════════════════════════════════════════════════════════════════════════════

class SetupSessionCreate(BaseModel):
    subscription_id: str | None = None
    context: dict | None = None


class SetupSessionMessage(BaseModel):
    message: str


@app.post("/api/setup/sessions", status_code=201)
async def start_setup_session(body: SetupSessionCreate, user: dict = Depends(_require_auth)):
    return _call_store(
        "create_setup_session",
        user_id=user["sub"],
        subscription_id=body.subscription_id,
        context=body.context,
    )


@app.get("/api/setup/sessions/{session_id}")
async def get_setup_session(session_id: str, user: dict = Depends(_require_auth)):
    result = _call_store("get_setup_session", session_id=session_id, user_id=user["sub"])
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@app.post("/api/setup/sessions/{session_id}/message")
async def advance_setup_session(
    session_id: str,
    body: SetupSessionMessage,
    user: dict = Depends(_require_auth),
):
    session = _call_store("get_setup_session", session_id=session_id, user_id=user["sub"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        from roxi.agents.interviewer import advance_session
        updated_session, reply, rules = advance_session(session, body.message)
    except ImportError:
        raise HTTPException(status_code=501, detail="roxi.agents.interviewer not available")

    _call_store(
        "save_setup_session",
        session_id=session_id,
        session=updated_session,
        user_id=user["sub"],
    )

    return {
        "reply": reply,
        "state": updated_session.get("state", "unknown"),
        "rules": rules,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Source health
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/subscriptions/{subscription_id}/sources")
async def list_source_health(subscription_id: str, user: dict = Depends(_require_auth)):
    return _call_store(
        "list_source_health",
        subscription_id=subscription_id,
        user_id=user["sub"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Scheduled runs
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/subscriptions/{subscription_id}/scheduled-runs")
async def list_scheduled_runs(
    subscription_id: str,
    limit: int = Query(20, le=100),
    user: dict = Depends(_require_auth),
):
    return _call_store(
        "list_scheduled_runs",
        subscription_id=subscription_id,
        user_id=user["sub"],
        limit=limit,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Lead feedback
# ═══════════════════════════════════════════════════════════════════════════════

class LeadFeedback(BaseModel):
    reason: str
    notes: str | None = None
    tags: list[str] | None = None


@app.post("/api/leads/{lead_id}/feedback", status_code=201)
async def add_lead_feedback(
    lead_id: str,
    body: LeadFeedback,
    user: dict = Depends(_require_auth),
):
    row = store.get_lead(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _call_store(
        "add_lead_feedback",
        lead_id=lead_id,
        user_id=user["sub"],
        reason=body.reason,
        notes=body.notes,
        tags=body.tags,
    )


@app.get("/api/leads/{lead_id}/feedback")
async def get_lead_feedback(lead_id: str, user: dict = Depends(_require_auth)):
    row = store.get_lead(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _call_store("list_lead_feedback", lead_id=lead_id, user_id=user["sub"])


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Results / analytics
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/subscriptions/{subscription_id}/results")
async def subscription_results(
    subscription_id: str,
    days: int = 30,
    user: dict = Depends(_require_auth),
):
    return _call_store(
        "get_subscription_results",
        subscription_id=subscription_id,
        user_id=user["sub"],
        days=days,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: Operator console (X-Operator-Key, not user JWT)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/operator/orgs")
async def operator_list_orgs(_op=Depends(_require_operator)):
    return _call_store("operator_list_orgs")


@app.get("/api/operator/source-health")
async def operator_source_health(_op=Depends(_require_operator)):
    return _call_store("operator_source_health")


@app.get("/api/operator/costs")
async def operator_costs(days: int = 30, _op=Depends(_require_operator)):
    return _call_store("operator_cost_breakdown", days=days)


@app.get("/api/operator/runs")
async def operator_runs(
    limit: int = Query(50, le=200),
    _op=Depends(_require_operator),
):
    return _call_store("operator_list_runs", limit=limit)
