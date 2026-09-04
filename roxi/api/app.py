"""
Roxi API server.

Endpoints:
  POST /slack/actions          — Slack interactive webhook (approve/reject)
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
  GET  /health                 — Deep health check (DB, env vars, Slack)
"""

from __future__ import annotations

import hashlib
import hmac
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


# ── Slack interactive webhook ────────────────────────────────────────────────

def _verify_slack_signature(body: bytes, timestamp: str | None, signature: str | None) -> bool:
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        # Refuse all Slack requests when the secret is not configured — safer than accepting.
        log.error("SLACK_SIGNING_SECRET not set — rejecting all /slack/actions requests")
        return False
    if not timestamp or not signature:
        return False
    # Reject stale requests to prevent replay attacks (Slack recommends ≤5 min).
    try:
        if abs(time.time() - float(timestamp)) > 300:
            log.warning("Slack timestamp too old — possible replay attack")
            return False
    except ValueError:
        return False
    basestring = f"v0:{timestamp}:{body.decode()}"
    mac = hmac.new(signing_secret.encode(), basestring.encode(), hashlib.sha256)
    expected = "v0=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/slack/actions")
@_rate_limit("30/minute")
async def slack_actions(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    if not _verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload_str = urllib.parse.unquote_plus(body.decode().removeprefix("payload="))
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    actions = payload.get("actions", [])
    if not actions:
        return Response(status_code=200)

    action = actions[0]
    decision = action.get("value", "")
    callback_id = payload.get("callback_id") or action.get("block_id", "")
    lead_id = callback_id

    if decision not in ("approved", "rejected"):
        log.warning("Unknown decision %r for lead %s", decision, lead_id)
        return Response(status_code=200)

    try:
        store.update_status(lead_id, decision)
        log.info("Lead %s → %s via Slack", lead_id, decision)
    except Exception as exc:
        log.error("Failed to update lead %s: %s", lead_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error updating lead status")

    return {"text": f"Lead marked {decision}."}


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
        "SLACK_WEBHOOK_URL", "SLACK_SIGNING_SECRET",
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

    # Slack connectivity check — run in a thread to avoid blocking the event loop.
    slack_url = os.environ.get("SLACK_WEBHOOK_URL")
    if slack_url:
        try:
            import anyio
            import requests as _req

            def _ping_slack() -> dict:
                t0 = time.perf_counter()
                r = _req.post(slack_url, json={"text": ""}, timeout=3)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                # Slack returns 400 "no_text" for empty — channel is live
                return {
                    "status": "ok" if r.status_code in (200, 400) else "error",
                    "http_status": r.status_code,
                    "latency_ms": latency_ms,
                }

            checks["slack"] = await anyio.to_thread.run_sync(_ping_slack)
        except Exception as exc:
            checks["slack"] = {"status": "error", "error": str(exc)}
    else:
        checks["slack"] = {"status": "not_configured"}

    return {"status": overall, "checks": checks}
