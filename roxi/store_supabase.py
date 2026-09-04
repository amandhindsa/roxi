"""
Supabase-backed store — complete drop-in replacement for store.py.

Activate by setting USE_SUPABASE=1 (plus SUPABASE_URL and SUPABASE_SERVICE_KEY).
store.py delegates to this module automatically when that env var is present.

Setup:
  1. Run scripts/setup_supabase.sql in your Supabase SQL editor.
  2. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env / Railway.
  3. Set USE_SUPABASE=1.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from roxi.models import EmailDraft, Lead, RawItem, ResearchBrief, Signal, ScoredSignal

log = logging.getLogger(__name__)

_client = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_client():
    global _client
    if _client is None:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


# ── Schema init ──────────────────────────────────────────────────────────────

def init_db(path: str | None = None) -> None:
    pass  # Schema managed via setup_supabase.sql


# ── Leads ────────────────────────────────────────────────────────────────────

def save(lead: Lead, vertical_id: str) -> None:
    sb = _get_client()
    result = sb.table("leads").upsert({
        "id": lead.id,
        "vertical_id": vertical_id,
        "raw_json": lead.raw.model_dump_json(),
        "signal_json": lead.signal.model_dump_json(),
        "scored_json": lead.scored.model_dump_json(),
        "research_json": lead.research.model_dump_json() if lead.research else None,
        "draft_json": lead.draft.model_dump_json() if lead.draft else None,
        "dedupe_key": lead.dedupe_key,
        "status": lead.status,
        "created_at": lead.created_at.isoformat() if hasattr(lead.created_at, "isoformat") else lead.created_at,
    }, on_conflict="dedupe_key", ignore_duplicates=True).execute()

    if not result.data:
        log.warning("store.save: dedupe_key collision for lead %s — not persisted", lead.id)
        return

    sb.table("dedupe_keys").upsert({
        "key": lead.dedupe_key,
        "created_at": _now(),
    }, on_conflict="key", ignore_duplicates=True).execute()


def update_status(lead_id: str, status: str) -> None:
    try:
        _get_client().table("leads").update({"status": status}).eq("id", lead_id).execute()
    except Exception as exc:
        log.error("store.update_status failed for lead %s → %s: %s", lead_id, status, exc)
        raise


def get_lead(lead_id: str) -> dict | None:
    result = _get_client().table("leads").select("*").eq("id", lead_id).limit(1).execute()
    if not result.data:
        return None
    return _row_to_api_dict(result.data[0])


def find_lead_by_short_id(short_id: str) -> dict | None:
    result = (
        _get_client()
        .table("leads")
        .select("*")
        .like("id", f"{short_id}%")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_api_dict(result.data[0])


def list_leads(
    vertical_id: str,
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    result = (
        _get_client()
        .table("leads")
        .select("*")
        .eq("vertical_id", vertical_id)
        .eq("status", status)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return [_row_to_api_dict(r) for r in result.data]


def pending_leads(vertical_id: str) -> list[Lead]:
    result = (
        _get_client()
        .table("leads")
        .select("*")
        .eq("vertical_id", vertical_id)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .execute()
    )
    return [_row_to_lead(r) for r in result.data]


def get_stats(vertical_id: str, days: int = 30) -> dict:
    sb = _get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    leads_result = (
        sb.table("leads")
        .select("status")
        .eq("vertical_id", vertical_id)
        .gte("created_at", cutoff)
        .execute()
    )
    status_counts: dict[str, int] = {}
    for r in leads_result.data:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    cost_result = (
        sb.table("llm_calls")
        .select("cost_usd")
        .gte("created_at", cutoff)
        .execute()
    )
    total_cost = sum(r["cost_usd"] or 0 for r in cost_result.data)
    total_calls = len(cost_result.data)

    total_leads = sum(status_counts.values())
    replied = status_counts.get("replied", 0)
    contacted = status_counts.get("sent", 0) + replied

    return {
        "vertical": vertical_id,
        "days": days,
        "leads": status_counts,
        "total_leads": total_leads,
        "reply_rate": round(replied / contacted, 3) if contacted else None,
        "llm_cost_usd": round(total_cost, 4),
        "llm_calls": total_calls,
    }


# ── Runs ─────────────────────────────────────────────────────────────────────

def start_run(vertical_id: str, org_id: str | None = None) -> str:
    run_id = str(uuid.uuid4())
    _get_client().table("runs").insert({
        "id": run_id,
        "vertical_id": vertical_id,
        "org_id": org_id,
        "started_at": _now(),
    }).execute()
    return run_id


def finish_run(
    run_id: str,
    *,
    raw_collected: int = 0,
    signals_extracted: int = 0,
    signals_qualified: int = 0,
    leads_delivered: int = 0,
    total_cost_usd: float = 0.0,
) -> None:
    _get_client().table("runs").update({
        "finished_at": _now(),
        "raw_collected": raw_collected,
        "signals_extracted": signals_extracted,
        "signals_qualified": signals_qualified,
        "leads_delivered": leads_delivered,
        "total_cost_usd": total_cost_usd,
    }).eq("id", run_id).execute()


def get_run_cost(run_id: str) -> float:
    result = (
        _get_client()
        .table("llm_calls")
        .select("cost_usd")
        .eq("run_id", run_id)
        .execute()
    )
    return sum(r["cost_usd"] or 0 for r in result.data)


def list_runs(vertical_id: str | None = None, limit: int = 20) -> list[dict]:
    q = _get_client().table("runs").select("*").order("started_at", desc=True).limit(limit)
    if vertical_id:
        q = q.eq("vertical_id", vertical_id)
    return q.execute().data


def get_run(run_id: str) -> dict | None:
    result = _get_client().table("runs").select("*").eq("id", run_id).limit(1).execute()
    return result.data[0] if result.data else None


# ── LLM call log ─────────────────────────────────────────────────────────────

def log_llm_call(
    *,
    model: str,
    agent: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    lead_id: str | None,
    run_id: str | None = None,
    org_id: str | None = None,
    prompt_version: str | None = None,
    input_hash: str | None = None,
    outcome: str | None = None,
) -> None:
    try:
        _get_client().table("llm_calls").insert({
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "org_id": org_id,
            "model": model,
            "agent": agent,
            "prompt_version": prompt_version,
            "input_hash": input_hash,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "outcome": outcome,
            "lead_id": lead_id,
            "created_at": _now(),
        }).execute()
    except Exception as exc:
        log.error("store.log_llm_call failed: %s", exc)


def list_llm_calls(run_id: str, limit: int = 200) -> list[dict]:
    return (
        _get_client()
        .table("llm_calls")
        .select("*")
        .eq("run_id", run_id)
        .order("created_at")
        .limit(limit)
        .execute()
        .data
    )


# ── Events ───────────────────────────────────────────────────────────────────

def list_events(
    run_id: str | None = None,
    agent: str | None = None,
    vertical_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    try:
        q = _get_client().table("events").select("*").order("created_at", desc=True).limit(limit)
        if run_id:
            q = q.eq("run_id", run_id)
        if agent:
            q = q.eq("agent", agent)
        if vertical_id:
            q = q.eq("vertical_id", vertical_id)
        return q.execute().data
    except Exception as exc:
        log.warning("store.list_events failed: %s", exc)
        return []


def daily_costs(days: int = 30, vertical_id: str | None = None) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = (
        _get_client()
        .table("llm_calls")
        .select("cost_usd, created_at")
        .gte("created_at", cutoff)
        .execute()
    )
    by_day: dict[str, dict] = {}
    for r in result.data:
        day = r["created_at"][:10]
        if day not in by_day:
            by_day[day] = {"day": day, "cost_usd": 0.0, "calls": 0}
        by_day[day]["cost_usd"] += r["cost_usd"] or 0
        by_day[day]["calls"] += 1
    return sorted(by_day.values(), key=lambda x: x["day"])


# ── Dedupe ───────────────────────────────────────────────────────────────────

def seen_dedupe_keys(days: int = 90) -> set[str]:
    """Return dedupe keys created within the last `days` days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = _get_client().table("dedupe_keys").select("key").gte("created_at", cutoff).execute()
    return {r["key"] for r in result.data}


def recent_company_names(days: int = 30) -> list[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = (
        _get_client()
        .table("leads")
        .select("signal_json")
        .gte("created_at", cutoff)
        .execute()
    )
    names = []
    for r in result.data:
        try:
            sig = json.loads(r["signal_json"])
            if sig.get("company"):
                names.append(sig["company"])
        except Exception:
            pass
    return names


# ── Suppression ───────────────────────────────────────────────────────────────

def is_suppressed(contact_identifier: str, channel: str) -> bool:
    result = (
        _get_client()
        .table("suppression_list")
        .select("id")
        .eq("contact_identifier", contact_identifier)
        .eq("channel", channel)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def add_to_suppression_list(
    contact_identifier: str, channel: str, reason: str
) -> None:
    try:
        _get_client().table("suppression_list").upsert({
            "id": str(uuid.uuid4()),
            "contact_identifier": contact_identifier,
            "channel": channel,
            "reason": reason,
            "added_at": _now(),
        }, on_conflict="contact_identifier,channel", ignore_duplicates=True).execute()
    except Exception as exc:
        log.error("store.add_to_suppression_list failed: %s", exc)


def list_suppression(channel: str | None = None, limit: int = 100) -> list[dict]:
    q = (
        _get_client()
        .table("suppression_list")
        .select("*")
        .order("added_at", desc=True)
        .limit(limit)
    )
    if channel:
        q = q.eq("channel", channel)
    return q.execute().data


def remove_from_suppression_list(contact_identifier: str, channel: str) -> bool:
    result = (
        _get_client()
        .table("suppression_list")
        .delete()
        .eq("contact_identifier", contact_identifier)
        .eq("channel", channel)
        .execute()
    )
    return bool(result.data)


# ── Stage outputs ─────────────────────────────────────────────────────────────

def log_stage_output(
    *,
    run_id: str,
    item_seq: int,
    stage: str,
    status: str,
    org_id: str | None = None,
    drop_reason: str | None = None,
    drop_detail: str | None = None,
    payload_json: str | None = None,
    source_url: str | None = None,
    company: str | None = None,
) -> None:
    try:
        _get_client().table("stage_outputs").insert({
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "org_id": org_id,
            "item_seq": item_seq,
            "stage": stage,
            "status": status,
            "drop_reason": drop_reason,
            "drop_detail": drop_detail,
            "payload_json": payload_json,
            "source_url": source_url,
            "company": company,
            "created_at": _now(),
        }).execute()
    except Exception as exc:
        log.error("store.log_stage_output failed run=%s stage=%s: %s", run_id, stage, exc)


# ── Publish log ───────────────────────────────────────────────────────────────

def log_publish(*, item_id: str, platform: str, result) -> None:
    try:
        _get_client().table("publish_log").insert({
            "id": str(uuid.uuid4()),
            "item_id": item_id,
            "platform": platform,
            "success": result.success,
            "post_url": result.post_url,
            "error": result.error,
            "created_at": _now(),
        }).execute()
    except Exception as exc:
        log.error("store.log_publish failed: %s", exc)


# ── Generation costs ──────────────────────────────────────────────────────────

def record_generation_cost(*, item_id: str, provider: str, cost_usd: float) -> None:
    try:
        _get_client().table("generation_costs").insert({
            "id": str(uuid.uuid4()),
            "item_id": item_id,
            "provider": provider,
            "cost_usd": cost_usd,
            "created_at": _now(),
        }).execute()
    except Exception as exc:
        log.error("store.record_generation_cost failed item=%s: %s", item_id, exc)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _row_to_api_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "vertical_id": row["vertical_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "scored": json.loads(row["scored_json"]) if row.get("scored_json") else {},
        "draft": json.loads(row["draft_json"]) if row.get("draft_json") else None,
        "research": json.loads(row["research_json"]) if row.get("research_json") else None,
    }


def _row_to_lead(row: dict) -> Lead:
    return Lead(
        id=row["id"],
        raw=RawItem.model_validate_json(row["raw_json"]),
        signal=Signal.model_validate_json(row["signal_json"]),
        scored=ScoredSignal.model_validate_json(row["scored_json"]),
        research=ResearchBrief.model_validate_json(row["research_json"]) if row.get("research_json") else None,
        draft=EmailDraft.model_validate_json(row["draft_json"]) if row.get("draft_json") else None,
        dedupe_key=row["dedupe_key"],
        status=row["status"],
        created_at=row["created_at"],
    )
