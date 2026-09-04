"""
Phase 5 — Supabase-backed store.

Drop-in replacement for store.py when SUPABASE_URL and SUPABASE_SERVICE_KEY
are set. The interface is identical: same function names and signatures.

Activate by setting USE_SUPABASE=1 in the environment.
store.py auto-delegates to this module when that env var is present.

Setup:
  1. Run scripts/setup_supabase.sql in your Supabase SQL editor.
  2. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env.
  3. Set USE_SUPABASE=1.

RLS: all tables have RLS enabled. The service key bypasses RLS for the API
server. The Next.js UI uses the anon key, which is restricted to SELECT on
leads and INSERT on lead_decisions via policy.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

from roxi.models import EmailDraft, Lead, RawItem, ResearchBrief, Signal, ScoredSignal

_client = None


def _get_client():
    global _client
    if _client is None:
        from supabase import create_client
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


def init_db(path: str | None = None) -> None:
    # No-op for Supabase — schema is managed via setup_supabase.sql
    pass


def save(lead: Lead, vertical_id: str) -> None:
    sb = _get_client()
    sb.table("leads").upsert({
        "id": lead.id,
        "vertical_id": vertical_id,
        "raw_json": lead.raw.model_dump_json(),
        "signal_json": lead.signal.model_dump_json(),
        "scored_json": lead.scored.model_dump_json(),
        "research_json": lead.research.model_dump_json() if lead.research else None,
        "draft_json": lead.draft.model_dump_json() if lead.draft else None,
        "dedupe_key": lead.dedupe_key,
        "status": lead.status,
        "created_at": lead.created_at.isoformat(),
    }, on_conflict="dedupe_key", ignore_duplicates=True).execute()

    sb.table("dedupe_keys").upsert({
        "key": lead.dedupe_key,
        "created_at": lead.created_at.isoformat(),
    }, on_conflict="key", ignore_duplicates=True).execute()


def update_status(lead_id: str, status: str) -> None:
    _get_client().table("leads").update({"status": status}).eq("id", lead_id).execute()


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


def recent_company_names(days: int = 30) -> list[str]:
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
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


def seen_dedupe_keys() -> set[str]:
    result = _get_client().table("dedupe_keys").select("key").execute()
    return {r["key"] for r in result.data}


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
        "created_at": datetime.utcnow().isoformat(),
    }).execute()


def log_publish(*, item_id: str, platform: str, result: "PublishResult") -> None:
    _get_client().table("publish_log").insert({
        "id": str(uuid.uuid4()),
        "item_id": item_id,
        "platform": platform,
        "success": result.success,
        "post_url": result.post_url,
        "error": result.error,
        "created_at": datetime.utcnow().isoformat(),
    }).execute()


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
