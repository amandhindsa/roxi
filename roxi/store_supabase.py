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

def save(lead: Lead, vertical_id: str, org_id: str | None = None, subscription_id: str | None = None) -> bool:
    """Persist lead. Returns True if inserted, False on dedupe_key collision."""
    sb = _get_client()
    result = sb.table("leads").upsert({
        "id": lead.id,
        "org_id": org_id,
        "vertical_id": vertical_id,
        "raw_json": lead.raw.model_dump_json(),
        "signal_json": lead.signal.model_dump_json(),
        "scored_json": lead.scored.model_dump_json(),
        "research_json": lead.research.model_dump_json() if lead.research else None,
        "draft_json": lead.draft.model_dump_json() if lead.draft else None,
        "dedupe_key": lead.dedupe_key,
        "status": lead.status,
        "contact_email": lead.contact_email,
        "subscription_id": subscription_id,
        "created_at": lead.created_at.isoformat() if hasattr(lead.created_at, "isoformat") else lead.created_at,
    }, on_conflict="dedupe_key", ignore_duplicates=True).execute()

    if not result.data:
        log.warning("store.save: dedupe_key collision for lead %s — not persisted", lead.id)
        return False

    sb.table("dedupe_keys").upsert({
        "key": lead.dedupe_key,
        "org_id": org_id,
        "subscription_id": subscription_id,
        "created_at": _now(),
    }, on_conflict="key", ignore_duplicates=True).execute()
    return True


def update_status(lead_id: str, status: str, rejection_reason: str | None = None) -> None:
    try:
        update_data: dict = {"status": status}
        if rejection_reason is not None:
            update_data["rejection_reason"] = rejection_reason
        _get_client().table("leads").update(update_data).eq("id", lead_id).execute()
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

def start_run(vertical_id: str, org_id: str | None = None,
              subscription_id: str | None = None) -> str:
    run_id = str(uuid.uuid4())
    _get_client().table("runs").insert({
        "id": run_id,
        "vertical_id": vertical_id,
        "org_id": org_id,
        "subscription_id": subscription_id,
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
    # Join llm_calls → runs to filter by vertical_id, mirroring the SQLite JOIN.
    # PostgREST embedded resource syntax: select from llm_calls, embed runs.
    q = (
        _get_client()
        .table("llm_calls")
        .select("cost_usd, created_at, runs(vertical_id)")
        .gte("created_at", cutoff)
    )
    if vertical_id:
        q = q.eq("runs.vertical_id", vertical_id)
    result = q.execute()
    by_day: dict[str, dict] = {}
    for r in result.data:
        day = r["created_at"][:10]
        if day not in by_day:
            by_day[day] = {"day": day, "cost_usd": 0.0, "calls": 0}
        by_day[day]["cost_usd"] += r["cost_usd"] or 0
        by_day[day]["calls"] += 1
    return sorted(by_day.values(), key=lambda x: x["day"])


# ── Dedupe ───────────────────────────────────────────────────────────────────

def seen_dedupe_keys(subscription_id: str | None = None, days: int = 90, org_id: str | None = None) -> set[str]:
    """Return dedupe keys created within the last `days` days, scoped by subscription_id or org_id."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = _get_client().table("dedupe_keys").select("key").gte("created_at", cutoff)
    if subscription_id is not None:
        q = q.eq("subscription_id", subscription_id)
    elif org_id:
        q = q.eq("org_id", org_id)
    result = q.execute()
    return {r["key"] for r in result.data}


def update_contact_email(lead_id: str, email: str) -> None:
    try:
        _get_client().table("leads").update({"contact_email": email}).eq("id", lead_id).execute()
    except Exception as exc:
        log.error("store.update_contact_email failed for lead %s: %s", lead_id, exc)
        raise


def recent_company_names(days: int = 30, org_id: str | None = None) -> list[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = _get_client().table("leads").select("signal_json").gte("created_at", cutoff)
    if org_id:
        q = q.eq("org_id", org_id)
    result = q.execute()
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
        "raw": json.loads(row["raw_json"]) if row.get("raw_json") else None,
        "signal": json.loads(row["signal_json"]) if row.get("signal_json") else None,
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
        contact_email=row.get("contact_email"),
        created_at=row["created_at"],
    )


# ── Organisations ─────────────────────────────────────────────────────────────

def create_org(name: str, slug: str) -> dict:
    row = {"id": str(uuid.uuid4()), "name": name, "slug": slug, "created_at": _now()}
    _get_client().table("organisations").insert(row).execute()
    return row

def get_org(org_id: str) -> dict | None:
    r = _get_client().table("organisations").select("*").eq("id", org_id).maybe_single().execute()
    return dict(r.data) if r.data else None

def get_org_by_slug(slug: str) -> dict | None:
    r = _get_client().table("organisations").select("*").eq("slug", slug).maybe_single().execute()
    return dict(r.data) if r.data else None

def list_orgs() -> list[dict]:
    r = _get_client().table("organisations").select("*").order("created_at").execute()
    return [dict(x) for x in r.data]

# ── Members ───────────────────────────────────────────────────────────────────

def add_member(org_id: str, user_id: str, email: str, role: str) -> dict:
    row = {"id": str(uuid.uuid4()), "org_id": org_id, "user_id": user_id,
           "email": email, "role": role, "invited_at": _now()}
    _get_client().table("members").insert(row).execute()
    return row

def get_member(org_id: str, user_id: str) -> dict | None:
    r = (_get_client().table("members").select("*")
         .eq("org_id", org_id).eq("user_id", user_id).maybe_single().execute())
    return dict(r.data) if r.data else None

def get_member_by_email(org_id: str, email: str) -> dict | None:
    r = (_get_client().table("members").select("*")
         .eq("org_id", org_id).eq("email", email).maybe_single().execute())
    return dict(r.data) if r.data else None

def list_members(org_id: str) -> list[dict]:
    r = _get_client().table("members").select("*").eq("org_id", org_id).execute()
    return [dict(x) for x in r.data]

def update_member_role(org_id: str, user_id: str, role: str) -> None:
    (_get_client().table("members").update({"role": role})
     .eq("org_id", org_id).eq("user_id", user_id).execute())

def remove_member(org_id: str, user_id: str) -> bool:
    r = (_get_client().table("members").delete()
         .eq("org_id", org_id).eq("user_id", user_id).execute())
    return bool(r.data)

def get_user_org(user_id: str) -> dict | None:
    r = _get_client().table("members").select("org_id").eq("user_id", user_id).limit(1).execute()
    if not r.data:
        return None
    org_id = r.data[0]["org_id"]
    return get_org(org_id)

# ── Subscriptions ─────────────────────────────────────────────────────────────

def create_subscription(org_id: str, vertical_id: str, **kwargs) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "vertical_id": vertical_id,
        "rules_version_id": kwargs.get("rules_version_id"),
        "status": kwargs.get("status", "active"),
        "paused": kwargs.get("paused", False),
        "daily_research_budget": kwargs.get("daily_research_budget", 15),
        "spend_ceiling_usd": kwargs.get("spend_ceiling_usd", 5.0),
        "qualify_threshold": kwargs.get("qualify_threshold", 70),
        "delivery_hour": kwargs.get("delivery_hour", 8),
        "delivery_timezone": kwargs.get("delivery_timezone", "America/Toronto"),
        "created_at": _now(),
    }
    _get_client().table("subscriptions").insert(row).execute()
    return row

def get_subscription(subscription_id: str) -> dict | None:
    r = _get_client().table("subscriptions").select("*").eq("id", subscription_id).maybe_single().execute()
    return dict(r.data) if r.data else None

def list_subscriptions(org_id: str) -> list[dict]:
    r = _get_client().table("subscriptions").select("*").eq("org_id", org_id).order("created_at").execute()
    return [dict(x) for x in r.data]

def update_subscription(subscription_id: str, **kwargs) -> None:
    _get_client().table("subscriptions").update(kwargs).eq("id", subscription_id).execute()

def list_active_subscriptions() -> list[dict]:
    r = (_get_client().table("subscriptions").select("*")
         .eq("status", "active").eq("paused", False).execute())
    return [dict(x) for x in r.data]

# ── Vertical rules ────────────────────────────────────────────────────────────

def save_vertical_rules(subscription_id: str, rules_json: str, icp_json: str,
                        product_brief: str, summary: str) -> dict:
    latest = get_latest_rules(subscription_id)
    version = (latest["version"] + 1) if latest else 1
    row = {
        "id": str(uuid.uuid4()),
        "subscription_id": subscription_id,
        "version": version,
        "rules_json": rules_json,
        "icp_json": icp_json,
        "product_brief": product_brief,
        "summary": summary,
        "created_at": _now(),
    }
    _get_client().table("vertical_rules").insert(row).execute()
    return row

def get_vertical_rules(rules_version_id: str) -> dict | None:
    r = _get_client().table("vertical_rules").select("*").eq("id", rules_version_id).maybe_single().execute()
    return dict(r.data) if r.data else None

def list_vertical_rules(subscription_id: str) -> list[dict]:
    r = (_get_client().table("vertical_rules").select("*")
         .eq("subscription_id", subscription_id).order("version", desc=True).execute())
    return [dict(x) for x in r.data]

def get_latest_rules(subscription_id: str) -> dict | None:
    r = (_get_client().table("vertical_rules").select("*")
         .eq("subscription_id", subscription_id).order("version", desc=True).limit(1).execute())
    return dict(r.data[0]) if r.data else None

# ── Setup sessions ────────────────────────────────────────────────────────────

def create_setup_session(org_id: str) -> dict:
    now = _now()
    row = {"id": str(uuid.uuid4()), "org_id": org_id, "state": "active",
           "messages_json": "[]", "created_at": now, "updated_at": now}
    _get_client().table("setup_sessions").insert(row).execute()
    return row

def get_setup_session(session_id: str) -> dict | None:
    r = _get_client().table("setup_sessions").select("*").eq("id", session_id).maybe_single().execute()
    return dict(r.data) if r.data else None

def update_setup_session(session_id: str, messages_json: str, state: str = "active",
                         subscription_id: str | None = None) -> None:
    payload: dict = {"messages_json": messages_json, "state": state, "updated_at": _now()}
    if subscription_id is not None:
        payload["subscription_id"] = subscription_id
    _get_client().table("setup_sessions").update(payload).eq("id", session_id).execute()

# ── Source health ─────────────────────────────────────────────────────────────

def record_source_health(subscription_id: str, source_name: str, count: int) -> None:
    existing = (_get_client().table("source_health").select("*")
                .eq("subscription_id", subscription_id).eq("source_name", source_name)
                .maybe_single().execute())
    now = _now()
    if existing.data:
        consecutive = 0 if count > 0 else (existing.data["consecutive_empty"] + 1)
        (_get_client().table("source_health").update({
            "last_run_at": now, "last_count": count, "consecutive_empty": consecutive,
        }).eq("subscription_id", subscription_id).eq("source_name", source_name).execute())
    else:
        _get_client().table("source_health").insert({
            "id": str(uuid.uuid4()), "subscription_id": subscription_id,
            "source_name": source_name, "last_run_at": now, "last_count": count,
            "consecutive_empty": 0 if count > 0 else 1, "created_at": now,
        }).execute()

def get_source_health(subscription_id: str) -> list[dict]:
    r = _get_client().table("source_health").select("*").eq("subscription_id", subscription_id).execute()
    return [dict(x) for x in r.data]

def get_quiet_sources(threshold: int = 3) -> list[dict]:
    r = (_get_client().table("source_health").select("*, subscriptions(org_id, vertical_id)")
         .gte("consecutive_empty", threshold).execute())
    return [dict(x) for x in r.data]

# ── Scheduled runs ────────────────────────────────────────────────────────────

def schedule_run(subscription_id: str, scheduled_at: str) -> dict:
    row = {"id": str(uuid.uuid4()), "subscription_id": subscription_id,
           "scheduled_at": scheduled_at, "status": "pending", "created_at": _now()}
    _get_client().table("scheduled_runs").insert(row).execute()
    return row

def claim_scheduled_run(scheduled_run_id: str) -> bool:
    # Only claim if currently pending (simple optimistic update)
    r = (_get_client().table("scheduled_runs")
         .update({"status": "running"})
         .eq("id", scheduled_run_id).eq("status", "pending").execute())
    return bool(r.data)

def complete_scheduled_run(scheduled_run_id: str, run_id: str, status: str = "done") -> None:
    (_get_client().table("scheduled_runs")
     .update({"status": status, "run_id": run_id})
     .eq("id", scheduled_run_id).execute())

def list_scheduled_runs(subscription_id: str, limit: int = 20) -> list[dict]:
    r = (_get_client().table("scheduled_runs").select("*")
         .eq("subscription_id", subscription_id)
         .order("scheduled_at", desc=True).limit(limit).execute())
    return [dict(x) for x in r.data]

# ── Lead feedback ─────────────────────────────────────────────────────────────

def add_lead_feedback(lead_id: str, reason: str, note: str | None = None) -> dict:
    row = {"id": str(uuid.uuid4()), "lead_id": lead_id, "reason": reason,
           "note": note, "created_at": _now()}
    _get_client().table("lead_feedback").insert(row).execute()
    return row

def list_lead_feedback(lead_id: str) -> list[dict]:
    r = _get_client().table("lead_feedback").select("*").eq("lead_id", lead_id).execute()
    return [dict(x) for x in r.data]

def get_rejection_reasons(subscription_id: str, days: int = 30) -> list[dict]:
    from datetime import timedelta, timezone as _tz
    cutoff = (datetime.now(_tz.utc) - timedelta(days=days)).isoformat()
    r = (_get_client().table("leads").select("id")
         .eq("subscription_id", subscription_id).gte("created_at", cutoff)
         .in_("status", ["rejected"]).execute())
    lead_ids = [x["id"] for x in r.data]
    if not lead_ids:
        return []
    fb = _get_client().table("lead_feedback").select("reason").in_("lead_id", lead_ids).execute()
    counts: dict[str, int] = {}
    for row in fb.data:
        counts[row["reason"]] = counts.get(row["reason"], 0) + 1
    return [{"reason": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

# ── Spend ceiling ─────────────────────────────────────────────────────────────

def get_subscription_spend_today(subscription_id: str) -> float:
    from datetime import date, timezone as _tz
    today = date.today().isoformat()
    r = (_get_client().table("runs").select("id")
         .eq("subscription_id", subscription_id)
         .gte("started_at", today).execute())
    run_ids = [x["id"] for x in r.data]
    if not run_ids:
        return 0.0
    calls = _get_client().table("llm_calls").select("cost_usd").in_("run_id", run_ids).execute()
    return float(sum(x["cost_usd"] or 0 for x in calls.data))

# ── Analytics ─────────────────────────────────────────────────────────────────

def get_reply_rates_by_score_band(subscription_id: str, days: int = 30) -> list[dict]:
    from datetime import timedelta, timezone as _tz
    cutoff = (datetime.now(_tz.utc) - timedelta(days=days)).isoformat()
    r = (_get_client().table("leads").select("scored_json, status")
         .eq("subscription_id", subscription_id).gte("created_at", cutoff).execute())
    bands = {"0-50": {"total": 0, "replied": 0},
             "50-60": {"total": 0, "replied": 0},
             "60-70": {"total": 0, "replied": 0},
             "70-80": {"total": 0, "replied": 0},
             "80-90": {"total": 0, "replied": 0},
             "90+":   {"total": 0, "replied": 0}}
    for row in r.data:
        scored = json.loads(row["scored_json"])
        score = scored.get("score", 0)
        band = ("0-50" if score < 50 else "50-60" if score < 60 else
                "60-70" if score < 70 else "70-80" if score < 80 else
                "80-90" if score < 90 else "90+")
        bands[band]["total"] += 1
        if row["status"] == "replied":
            bands[band]["replied"] += 1
    return [{"band": k, "total": v["total"], "replied": v["replied"],
             "rate": round(v["replied"] / v["total"], 3) if v["total"] else None}
            for k, v in bands.items()]

def get_subscription_stats(subscription_id: str, days: int = 30) -> dict:
    from datetime import timedelta, timezone as _tz
    cutoff = (datetime.now(_tz.utc) - timedelta(days=days)).isoformat()
    r = (_get_client().table("leads").select("status")
         .eq("subscription_id", subscription_id).gte("created_at", cutoff).execute())
    status_counts: dict[str, int] = {}
    for row in r.data:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    total = sum(status_counts.values())
    replied = status_counts.get("replied", 0)
    approved = status_counts.get("approved", 0)
    return {
        "subscription_id": subscription_id,
        "days": days,
        "total_leads": total,
        "leads": status_counts,
        "reply_rate": round(replied / total, 3) if total else None,
        "approval_rate": round(approved / total, 3) if total else None,
    }


