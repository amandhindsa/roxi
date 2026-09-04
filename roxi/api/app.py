"""
Roxi API server.

Endpoints:
  POST /whatsapp/webhook       — Twilio WhatsApp webhook (approve/reject via reply)
  GET  /api/leads              — List leads with filters
  GET  /api/leads/{id}         — Single lead
  PATCH /api/leads/{id}        — Update lead status (requires ROXI_API_KEY)
  GET  /api/stats              — Funnel + cost stats
  GET  /api/runs               — Pipeline run history
  GET  /api/runs/{id}          — Single run detail + LLM call breakdown
  GET  /api/telemetry/events   — Structured event log
  GET  /api/telemetry/costs    — Daily cost series
  GET  /api/suppression        — Suppression list entries
  DELETE /api/suppression      — Remove an entry (requires ROXI_API_KEY)
  GET  /healthz                — Liveness probe (process alive)
  GET  /readyz                 — Readiness probe (DB + required env vars)
  GET  /health                 — Deep health check (DB, env vars, Twilio)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from roxi import store
from roxi.models import Lead

log = logging.getLogger(__name__)

app = FastAPI(title="Roxi API", version="0.3.0")

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

limiter = None  # defined before try so _rate_limit() never hits NameError
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


# ── Auth ─────────────────────────────────────────────────────────────────────

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


store.init_db()


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

    # Resolve short id (first 8 chars) to full lead id
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
):
    return store.list_leads(vertical_id=vertical, status=status, limit=limit, offset=offset)


@app.get("/api/leads/{lead_id}")
async def get_lead(lead_id: str):
    row = store.get_lead(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return row


class StatusUpdate(BaseModel):
    status: str


@app.patch("/api/leads/{lead_id}")
async def update_lead_status(lead_id: str, body: StatusUpdate, _auth=Depends(_require_api_key)):
    allowed = {"approved", "rejected", "sent", "replied"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    row = store.get_lead(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    store.update_status(lead_id, body.status)
    log.info("Lead %s → %s via API", lead_id, body.status)
    return {"id": lead_id, "status": body.status}


# ── Stats ────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats(vertical: str = "hauler_ai", days: int = 30):
    return store.get_stats(vertical_id=vertical, days=days)


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

    # DB
    try:
        with store._conn() as con:
            con.execute("SELECT 1").fetchone()
    except Exception as exc:
        issues.append(f"db: {exc}")

    # Required env
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

    # Required env vars
    required_vars = ["ANTHROPIC_API_KEY"]
    optional_vars = [
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
        "TWILIO_WHATSAPP_FROM", "WHATSAPP_TO",
        "INSTANTLY_API_KEY", "INSTANTLY_CAMPAIGN_ID",
        "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
        "ROXI_API_KEY",
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

    # Twilio connectivity check — run in a thread to avoid blocking the event loop.
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
