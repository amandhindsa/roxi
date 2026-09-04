from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from roxi.models import Lead

log = logging.getLogger(__name__)

# Delegate to Supabase backend when USE_SUPABASE=1 is set.
# sys.modules replacement ensures all callers get the Supabase module on subsequent imports;
# the SQLite definitions below are harmless — they're never called when USE_SUPABASE=1
# because every call site imports roxi.store fresh and gets the replaced module.
if os.environ.get("USE_SUPABASE") == "1":
    import sys
    from roxi.store_supabase import *  # noqa: F401, F403
    from roxi.store_supabase import _now  # noqa: F401
    sys.modules[__name__] = sys.modules["roxi.store_supabase"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _db_path() -> str:
    return os.environ.get("ROXI_DB_PATH", "roxi.db")


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(path: str | None = None) -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                org_id TEXT,
                vertical_id TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                signal_json TEXT NOT NULL,
                scored_json TEXT NOT NULL,
                research_json TEXT,
                draft_json TEXT,
                dedupe_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                contact_email TEXT,
                created_at TEXT NOT NULL,
                subscription_id TEXT,
                rejection_reason TEXT,
                draft_edited_json TEXT
            );
            CREATE TABLE IF NOT EXISTS dedupe_keys (
                key TEXT PRIMARY KEY,
                org_id TEXT,
                created_at TEXT NOT NULL,
                subscription_id TEXT
            );
            -- Phase 4: trace table — one row per agent call, per pipeline run
            CREATE TABLE IF NOT EXISTS llm_calls (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                org_id TEXT,
                model TEXT NOT NULL,
                agent TEXT NOT NULL,
                prompt_version TEXT,
                input_hash TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost_usd REAL,
                latency_ms INTEGER,
                outcome TEXT,
                lead_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                vertical_id TEXT NOT NULL,
                org_id TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                raw_collected INTEGER DEFAULT 0,
                signals_extracted INTEGER DEFAULT 0,
                signals_qualified INTEGER DEFAULT 0,
                leads_delivered INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0,
                subscription_id TEXT,
                rules_version_id TEXT
            );
            -- Suppression list: enforced by Dispatcher before every send
            CREATE TABLE IF NOT EXISTS suppression_list (
                id TEXT PRIMARY KEY,
                contact_identifier TEXT NOT NULL,
                channel TEXT NOT NULL,
                reason TEXT NOT NULL,
                added_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS suppression_unique
                ON suppression_list(contact_identifier, channel);
            CREATE TABLE IF NOT EXISTS publish_log (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                success INTEGER NOT NULL,
                post_url TEXT,
                error TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                event TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'info',
                run_id TEXT,
                org_id TEXT,
                vertical_id TEXT,
                agent TEXT,
                lead_id TEXT,
                data_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS generation_costs (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                cost_usd REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            -- Stage-level observability: one row per item per stage, including drops
            CREATE TABLE IF NOT EXISTS stage_outputs (
                id           TEXT PRIMARY KEY,
                run_id       TEXT NOT NULL,
                org_id       TEXT,
                item_seq     INTEGER NOT NULL,
                stage        TEXT NOT NULL,
                status       TEXT NOT NULL,
                drop_reason  TEXT,
                drop_detail  TEXT,
                payload_json TEXT,
                source_url   TEXT,
                company      TEXT,
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS stage_outputs_run
                ON stage_outputs(run_id, stage);
            CREATE INDEX IF NOT EXISTS stage_outputs_company
                ON stage_outputs(company);
            CREATE INDEX IF NOT EXISTS stage_outputs_reason
                ON stage_outputs(drop_reason);
            CREATE TABLE IF NOT EXISTS organisations (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                slug        TEXT UNIQUE NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS members (
                id          TEXT PRIMARY KEY,
                org_id      TEXT NOT NULL REFERENCES organisations(id),
                user_id     TEXT NOT NULL,
                email       TEXT NOT NULL,
                role        TEXT NOT NULL CHECK (role IN ('owner','reviewer','viewer')),
                invited_at  TEXT NOT NULL,
                joined_at   TEXT,
                UNIQUE (org_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                id                      TEXT PRIMARY KEY,
                org_id                  TEXT NOT NULL REFERENCES organisations(id),
                vertical_id             TEXT NOT NULL,
                rules_version_id        TEXT,
                status                  TEXT NOT NULL DEFAULT 'active',
                paused                  INTEGER NOT NULL DEFAULT 0,
                daily_research_budget   INTEGER NOT NULL DEFAULT 15,
                spend_ceiling_usd       REAL NOT NULL DEFAULT 5.0,
                qualify_threshold       INTEGER NOT NULL DEFAULT 70,
                delivery_hour           INTEGER NOT NULL DEFAULT 8,
                delivery_timezone       TEXT NOT NULL DEFAULT 'America/Toronto',
                created_at              TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS vertical_rules (
                id              TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
                version         INTEGER NOT NULL,
                rules_json      TEXT NOT NULL,
                icp_json        TEXT NOT NULL,
                product_brief   TEXT NOT NULL,
                summary         TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                UNIQUE (subscription_id, version)
            );
            CREATE TABLE IF NOT EXISTS setup_sessions (
                id              TEXT PRIMARY KEY,
                org_id          TEXT NOT NULL REFERENCES organisations(id),
                subscription_id TEXT,
                state           TEXT NOT NULL DEFAULT 'active',
                messages_json   TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_health (
                id                  TEXT PRIMARY KEY,
                subscription_id     TEXT NOT NULL REFERENCES subscriptions(id),
                source_name         TEXT NOT NULL,
                last_run_at         TEXT,
                last_count          INTEGER NOT NULL DEFAULT 0,
                consecutive_empty   INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL,
                UNIQUE (subscription_id, source_name)
            );
            CREATE TABLE IF NOT EXISTS scheduled_runs (
                id              TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
                scheduled_at    TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                run_id          TEXT,
                created_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lead_feedback (
                id          TEXT PRIMARY KEY,
                lead_id     TEXT NOT NULL REFERENCES leads(id),
                reason      TEXT NOT NULL,
                note        TEXT,
                created_at  TEXT NOT NULL
            );
        """)
    log.debug("init_db complete: %s", _db_path())


def save(lead: Lead, vertical_id: str, org_id: str | None = None, subscription_id: str | None = None) -> bool:
    """Persist lead. Returns True if inserted, False on dedupe_key collision."""
    try:
        return _save(lead, vertical_id, org_id, subscription_id)
    except Exception as exc:
        log.error("store.save failed for lead %s: %s", lead.id, exc, exc_info=True)
        raise


def _save(lead: Lead, vertical_id: str, org_id: str | None = None, subscription_id: str | None = None) -> bool:
    """Return True if the lead was actually inserted (False = dedupe_key collision)."""
    with _conn() as con:
        cur = con.execute(
            """INSERT OR IGNORE INTO leads
               (id, org_id, vertical_id, raw_json, signal_json, scored_json,
                research_json, draft_json, dedupe_key, status, contact_email, created_at,
                subscription_id, rejection_reason, draft_edited_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lead.id,
                org_id,
                vertical_id,
                lead.raw.model_dump_json(),
                lead.signal.model_dump_json(),
                lead.scored.model_dump_json(),
                lead.research.model_dump_json() if lead.research else None,
                lead.draft.model_dump_json() if lead.draft else None,
                lead.dedupe_key,
                lead.status,
                lead.contact_email,
                lead.created_at.isoformat(),
                subscription_id,
                None,
                None,
            ),
        )
        inserted = cur.rowcount > 0
        if not inserted:
            log.warning(
                "store.save: dedupe_key collision for lead %s (key=%s) — not persisted",
                lead.id,
                lead.dedupe_key,
            )
            return False
        con.execute(
            "INSERT OR IGNORE INTO dedupe_keys (key, org_id, created_at, subscription_id) VALUES (?,?,?,?)",
            (lead.dedupe_key, org_id, lead.created_at.isoformat(), subscription_id),
        )
        return True


def update_status(lead_id: str, status: str, rejection_reason: str | None = None) -> None:
    try:
        with _conn() as con:
            if rejection_reason is not None:
                con.execute(
                    "UPDATE leads SET status=?, rejection_reason=? WHERE id=?",
                    (status, rejection_reason, lead_id),
                )
            else:
                con.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
    except Exception as exc:
        log.error("store.update_status failed for lead %s → %s: %s", lead_id, status, exc, exc_info=True)
        raise


def update_contact_email(lead_id: str, email: str) -> None:
    try:
        with _conn() as con:
            con.execute("UPDATE leads SET contact_email=? WHERE id=?", (email, lead_id))
    except Exception as exc:
        log.error("store.update_contact_email failed for lead %s: %s", lead_id, exc, exc_info=True)
        raise


def get_lead(lead_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        return None
    return _row_to_api_dict(row)


def find_lead_by_short_id(short_id: str) -> dict | None:
    """Resolve the first 8 characters of a lead ID to the full lead row."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM leads WHERE id LIKE ? LIMIT 1", (short_id + "%",)
        ).fetchone()
    if not row:
        return None
    return _row_to_api_dict(row)


def list_leads(
    vertical_id: str,
    status: str = "pending",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM leads
               WHERE vertical_id=? AND status=?
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (vertical_id, status, limit, offset),
        ).fetchall()
    return [_row_to_api_dict(r) for r in rows]


def get_stats(vertical_id: str, days: int = 30) -> dict:
    with _conn() as con:
        status_rows = con.execute(
            """SELECT status, COUNT(*) as n FROM leads
               WHERE vertical_id=? AND created_at >= datetime('now', ?)
               GROUP BY status""",
            (vertical_id, f"-{days} days"),
        ).fetchall()
        cost_row = con.execute(
            """SELECT SUM(cost_usd) as total_cost, COUNT(*) as calls
               FROM llm_calls WHERE created_at >= datetime('now', ?)""",
            (f"-{days} days",),
        ).fetchone()

    status_counts = {r["status"]: r["n"] for r in status_rows}
    total_leads = sum(status_counts.values())
    replied = status_counts.get("replied", 0)
    # "sent" means attempted contact; replied is a subset of that, so don't double-count.
    contacted = status_counts.get("sent", 0) + replied

    return {
        "vertical": vertical_id,
        "days": days,
        "leads": status_counts,
        "total_leads": total_leads,
        "reply_rate": round(replied / contacted, 3) if contacted else None,
        "llm_cost_usd": round(cost_row["total_cost"] or 0, 4),
        "llm_calls": cost_row["calls"] or 0,
    }


def list_runs(vertical_id: str | None = None, limit: int = 20) -> list[dict]:
    with _conn() as con:
        if vertical_id:
            rows = con.execute(
                "SELECT * FROM runs WHERE vertical_id=? ORDER BY started_at DESC LIMIT ?",
                (vertical_id, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_llm_calls(run_id: str, limit: int = 200) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM llm_calls WHERE run_id=?
               ORDER BY created_at ASC LIMIT ?""",
            (run_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_events(
    run_id: str | None = None,
    agent: str | None = None,
    vertical_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    try:  # noqa: SIM105  — intentional: telemetry must never surface errors to callers
        clauses = []
        params: list = []
        if run_id:
            clauses.append("run_id=?")
            params.append(run_id)
        if agent:
            clauses.append("agent=?")
            params.append(agent)
        if vertical_id:
            clauses.append("vertical_id=?")
            params.append(vertical_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with _conn() as con:
            rows = con.execute(
                f"SELECT * FROM events {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("store.list_events failed: %s", exc)
        return []


def daily_costs(days: int = 30, vertical_id: str | None = None) -> list[dict]:
    with _conn() as con:
        if vertical_id:
            rows = con.execute(
                """SELECT date(lc.created_at) as day,
                          SUM(lc.cost_usd) as cost_usd,
                          COUNT(*) as calls
                   FROM llm_calls lc
                   JOIN runs r ON r.id = lc.run_id
                   WHERE r.vertical_id=? AND lc.created_at >= datetime('now', ?)
                   GROUP BY day ORDER BY day""",
                (vertical_id, f"-{days} days"),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT date(created_at) as day,
                          SUM(cost_usd) as cost_usd,
                          COUNT(*) as calls
                   FROM llm_calls
                   WHERE created_at >= datetime('now', ?)
                   GROUP BY day ORDER BY day""",
                (f"-{days} days",),
            ).fetchall()
    return [dict(r) for r in rows]


def pending_leads(vertical_id: str) -> list[Lead]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM leads WHERE vertical_id=? AND status='pending'",
            (vertical_id,),
        ).fetchall()
    return [_row_to_lead(r) for r in rows]


def recent_company_names(days: int = 30, org_id: str | None = None) -> list[str]:
    with _conn() as con:
        if org_id:
            rows = con.execute(
                """SELECT signal_json FROM leads
                   WHERE org_id=? AND created_at >= datetime('now', ?)""",
                (org_id, f"-{days} days"),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT signal_json FROM leads
                   WHERE created_at >= datetime('now', ?)""",
                (f"-{days} days",),
            ).fetchall()
    names = []
    for r in rows:
        sig = json.loads(r["signal_json"])
        if sig.get("company"):
            names.append(sig["company"])
    return names


def seen_dedupe_keys(subscription_id: str | None = None, days: int = 90, org_id: str | None = None) -> set[str]:
    """Return dedupe keys created within the last `days` days.

    Bounded to avoid loading the entire table into memory forever.
    90 days keeps a meaningful repeat-contact window without unbounded growth.
    When subscription_id is provided, only keys for that subscription are returned.
    When org_id is provided (legacy), only keys for that org are returned.
    """
    with _conn() as con:
        if subscription_id is not None:
            rows = con.execute(
                "SELECT key FROM dedupe_keys WHERE created_at >= datetime('now', ?) AND subscription_id=?",
                (f"-{days} days", subscription_id),
            ).fetchall()
        elif org_id:
            rows = con.execute(
                "SELECT key FROM dedupe_keys WHERE org_id=? AND created_at >= datetime('now', ?)",
                (org_id, f"-{days} days"),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT key FROM dedupe_keys WHERE created_at >= datetime('now', ?)",
                (f"-{days} days",),
            ).fetchall()
    return {r["key"] for r in rows}


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
        _log_llm_call_inner(model=model, agent=agent, input_tokens=input_tokens,
                            output_tokens=output_tokens, cost_usd=cost_usd, latency_ms=latency_ms,
                            lead_id=lead_id, run_id=run_id, org_id=org_id,
                            prompt_version=prompt_version, input_hash=input_hash, outcome=outcome)
    except Exception as exc:
        log.error("store.log_llm_call failed agent=%s run=%s: %s", agent, run_id, exc)


def _log_llm_call_inner(
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
    with _conn() as con:
        con.execute(
            """INSERT INTO llm_calls
               (id, run_id, org_id, model, agent, prompt_version, input_hash,
                input_tokens, output_tokens, cost_usd, latency_ms, outcome, lead_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                run_id,
                org_id,
                model,
                agent,
                prompt_version,
                input_hash,
                input_tokens,
                output_tokens,
                cost_usd,
                latency_ms,
                outcome,
                lead_id,
                _now(),
            ),
        )


def get_run_cost(run_id: str) -> float:
    """Public method to tally LLM cost for a run without exposing _conn."""
    try:
        with _conn() as con:
            row = con.execute(
                "SELECT SUM(cost_usd) FROM llm_calls WHERE run_id=?", (run_id,)
            ).fetchone()
        return float(row[0] or 0.0)
    except Exception as exc:
        log.warning("store.get_run_cost failed for run %s: %s", run_id, exc)
        return 0.0


def start_run(vertical_id: str, org_id: str | None = None,
              subscription_id: str | None = None) -> str:
    log.debug("store.start_run: vertical=%s org=%s sub=%s", vertical_id, org_id, subscription_id)
    run_id = str(uuid.uuid4())
    try:
        with _conn() as con:
            con.execute(
                """INSERT INTO runs (id, vertical_id, org_id, subscription_id, started_at)
                   VALUES (?,?,?,?,?)""",
                (run_id, vertical_id, org_id, subscription_id, _now()),
            )
    except Exception as exc:
        log.error("store.start_run failed vertical=%s: %s", vertical_id, exc, exc_info=True)
        raise
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
    try:
        with _conn() as con:
            con.execute(
                """UPDATE runs SET finished_at=?, raw_collected=?, signals_extracted=?,
                   signals_qualified=?, leads_delivered=?, total_cost_usd=?
                   WHERE id=?""",
                (
                    _now(),
                    raw_collected,
                    signals_extracted,
                    signals_qualified,
                    leads_delivered,
                    total_cost_usd,
                    run_id,
                ),
            )
    except Exception as exc:
        log.error("store.finish_run failed run=%s: %s", run_id, exc, exc_info=True)


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
        with _conn() as con:
            con.execute(
                """INSERT INTO stage_outputs
                   (id, run_id, org_id, item_seq, stage, status,
                    drop_reason, drop_detail, payload_json, source_url, company, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    run_id,
                    org_id,
                    item_seq,
                    stage,
                    status,
                    drop_reason,
                    drop_detail,
                    payload_json,
                    source_url,
                    company,
                    _now(),
                ),
            )
    except Exception as exc:
        log.error("store.log_stage_output failed run=%s stage=%s: %s", run_id, stage, exc)


def add_to_suppression_list(contact_identifier: str, channel: str, reason: str) -> None:
    try:
        with _conn() as con:
            con.execute(
                """INSERT OR IGNORE INTO suppression_list
                   (id, contact_identifier, channel, reason, added_at)
                   VALUES (?,?,?,?,?)""",
                (str(uuid.uuid4()), contact_identifier, channel, reason, _now()),
            )
    except Exception as exc:
        log.error("store.add_to_suppression_list failed %s/%s: %s", contact_identifier, channel, exc, exc_info=True)
        raise


def is_suppressed(contact_identifier: str, channel: str) -> bool:
    with _conn() as con:
        row = con.execute(
            """SELECT 1 FROM suppression_list
               WHERE contact_identifier=? AND channel=?""",
            (contact_identifier, channel),
        ).fetchone()
    return row is not None


def list_suppression(channel: str | None = None, limit: int = 100) -> list[dict]:
    with _conn() as con:
        if channel:
            rows = con.execute(
                "SELECT * FROM suppression_list WHERE channel=? ORDER BY added_at DESC LIMIT ?",
                (channel, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM suppression_list ORDER BY added_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def remove_from_suppression_list(contact_identifier: str, channel: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM suppression_list WHERE contact_identifier=? AND channel=?",
            (contact_identifier, channel),
        )
        deleted = cur.rowcount > 0
    return deleted


def log_publish(*, item_id: str, platform: str, result: "PublishResult") -> None:
    """Audit row for every publish attempt (success or failure)."""
    with _conn() as con:
        con.execute(
            """INSERT INTO publish_log
               (id, item_id, platform, success, post_url, error, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                item_id,
                platform,
                int(result.success),
                result.post_url,
                result.error,
                _now(),
            ),
        )


def record_generation_cost(*, item_id: str, provider: str, cost_usd: float) -> None:
    """Record an image/video generation cost. Schema owned by init_db."""
    try:
        with _conn() as con:
            con.execute(
                "INSERT INTO generation_costs (id, item_id, provider, cost_usd, created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), item_id, provider, cost_usd, _now()),
            )
    except Exception as exc:
        log.error("store.record_generation_cost failed item=%s: %s", item_id, exc)


def _row_to_api_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("raw_json", "signal_json", "scored_json", "research_json", "draft_json"):
        if d.get(key):
            d[key.replace("_json", "")] = json.loads(d.pop(key))
        else:
            d.pop(key, None)
    return d


def _row_to_lead(row: sqlite3.Row) -> Lead:
    from roxi.models import EmailDraft, RawItem, ResearchBrief, Signal, ScoredSignal

    return Lead(
        id=row["id"],
        raw=RawItem.model_validate_json(row["raw_json"]),
        signal=Signal.model_validate_json(row["signal_json"]),
        scored=ScoredSignal.model_validate_json(row["scored_json"]),
        research=ResearchBrief.model_validate_json(row["research_json"]) if row["research_json"] else None,
        draft=EmailDraft.model_validate_json(row["draft_json"]) if row["draft_json"] else None,
        dedupe_key=row["dedupe_key"],
        status=row["status"],
        contact_email=row["contact_email"] if "contact_email" in row.keys() else None,
        created_at=row["created_at"],
    )


# ── Organisations ─────────────────────────────────────────────────────────────

def create_org(name: str, slug: str) -> dict:
    org_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO organisations (id, name, slug, created_at) VALUES (?,?,?,?)",
            (org_id, name, slug, now),
        )
    return {"id": org_id, "name": name, "slug": slug, "created_at": now}


def get_org(org_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM organisations WHERE id=?", (org_id,)).fetchone()
    return dict(row) if row else None


def get_org_by_slug(slug: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM organisations WHERE slug=?", (slug,)).fetchone()
    return dict(row) if row else None


def list_orgs() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM organisations ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


# ── Members ───────────────────────────────────────────────────────────────────

def add_member(org_id: str, user_id: str, email: str, role: str) -> dict:
    member_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            """INSERT INTO members (id, org_id, user_id, email, role, invited_at)
               VALUES (?,?,?,?,?,?)""",
            (member_id, org_id, user_id, email, role, now),
        )
    return {"id": member_id, "org_id": org_id, "user_id": user_id,
            "email": email, "role": role, "invited_at": now, "joined_at": None}


def get_member(org_id: str, user_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM members WHERE org_id=? AND user_id=?", (org_id, user_id)
        ).fetchone()
    return dict(row) if row else None


def get_member_by_email(org_id: str, email: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM members WHERE org_id=? AND email=?", (org_id, email)
        ).fetchone()
    return dict(row) if row else None


def list_members(org_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM members WHERE org_id=? ORDER BY invited_at ASC", (org_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_member_role(org_id: str, user_id: str, role: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE members SET role=? WHERE org_id=? AND user_id=?",
            (role, org_id, user_id),
        )


def remove_member(org_id: str, user_id: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM members WHERE org_id=? AND user_id=?", (org_id, user_id)
        )
    return cur.rowcount > 0


def get_user_org(user_id: str) -> dict | None:
    """Returns the org dict for a user, or None."""
    with _conn() as con:
        row = con.execute(
            """SELECT o.* FROM organisations o
               JOIN members m ON m.org_id = o.id
               WHERE m.user_id=? LIMIT 1""",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


# ── Subscriptions ─────────────────────────────────────────────────────────────

def create_subscription(org_id: str, vertical_id: str, **kwargs) -> dict:
    sub_id = str(uuid.uuid4())
    now = _now()
    row = {
        "id": sub_id,
        "org_id": org_id,
        "vertical_id": vertical_id,
        "rules_version_id": kwargs.get("rules_version_id"),
        "status": kwargs.get("status", "active"),
        "paused": int(kwargs.get("paused", 0)),
        "daily_research_budget": kwargs.get("daily_research_budget", 15),
        "spend_ceiling_usd": kwargs.get("spend_ceiling_usd", 5.0),
        "qualify_threshold": kwargs.get("qualify_threshold", 70),
        "delivery_hour": kwargs.get("delivery_hour", 8),
        "delivery_timezone": kwargs.get("delivery_timezone", "America/Toronto"),
        "created_at": now,
    }
    with _conn() as con:
        con.execute(
            """INSERT INTO subscriptions
               (id, org_id, vertical_id, rules_version_id, status, paused,
                daily_research_budget, spend_ceiling_usd, qualify_threshold,
                delivery_hour, delivery_timezone, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["id"], row["org_id"], row["vertical_id"], row["rules_version_id"],
                row["status"], row["paused"], row["daily_research_budget"],
                row["spend_ceiling_usd"], row["qualify_threshold"],
                row["delivery_hour"], row["delivery_timezone"], row["created_at"],
            ),
        )
    return row


def get_subscription(subscription_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM subscriptions WHERE id=?", (subscription_id,)
        ).fetchone()
    return dict(row) if row else None


def list_subscriptions(org_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM subscriptions WHERE org_id=? ORDER BY created_at DESC",
            (org_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_subscription(subscription_id: str, **kwargs) -> None:
    if not kwargs:
        return
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [subscription_id]
    with _conn() as con:
        con.execute(
            f"UPDATE subscriptions SET {fields} WHERE id=?", values
        )


def list_active_subscriptions() -> list[dict]:
    """All non-paused active subscriptions. Used by scheduler."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM subscriptions WHERE status='active' AND paused=0"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Vertical rules ────────────────────────────────────────────────────────────

def save_vertical_rules(
    subscription_id: str,
    rules_json: str,
    icp_json: str,
    product_brief: str,
    summary: str,
) -> dict:
    """Create a new version. Increments version number. Returns the saved row."""
    rule_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        row = con.execute(
            "SELECT COALESCE(MAX(version), 0) as max_v FROM vertical_rules WHERE subscription_id=?",
            (subscription_id,),
        ).fetchone()
        next_version = (row["max_v"] if row else 0) + 1
        con.execute(
            """INSERT INTO vertical_rules
               (id, subscription_id, version, rules_json, icp_json, product_brief, summary, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (rule_id, subscription_id, next_version, rules_json, icp_json, product_brief, summary, now),
        )
    return {
        "id": rule_id,
        "subscription_id": subscription_id,
        "version": next_version,
        "rules_json": rules_json,
        "icp_json": icp_json,
        "product_brief": product_brief,
        "summary": summary,
        "created_at": now,
    }


def get_vertical_rules(rules_version_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM vertical_rules WHERE id=?", (rules_version_id,)
        ).fetchone()
    return dict(row) if row else None


def list_vertical_rules(subscription_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM vertical_rules WHERE subscription_id=? ORDER BY version DESC",
            (subscription_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_rules(subscription_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            """SELECT * FROM vertical_rules WHERE subscription_id=?
               ORDER BY version DESC LIMIT 1""",
            (subscription_id,),
        ).fetchone()
    return dict(row) if row else None


# ── Setup sessions ────────────────────────────────────────────────────────────

def create_setup_session(org_id: str) -> dict:
    session_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            """INSERT INTO setup_sessions
               (id, org_id, subscription_id, state, messages_json, created_at, updated_at)
               VALUES (?,?,NULL,'active','[]',?,?)""",
            (session_id, org_id, now, now),
        )
    return {
        "id": session_id,
        "org_id": org_id,
        "subscription_id": None,
        "state": "active",
        "messages_json": "[]",
        "created_at": now,
        "updated_at": now,
    }


def get_setup_session(session_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM setup_sessions WHERE id=?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def update_setup_session(
    session_id: str,
    messages_json: str,
    state: str = "active",
    subscription_id: str | None = None,
) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE setup_sessions
               SET messages_json=?, state=?, subscription_id=COALESCE(?,subscription_id),
                   updated_at=?
               WHERE id=?""",
            (messages_json, state, subscription_id, _now(), session_id),
        )


# ── Source health ─────────────────────────────────────────────────────────────

def record_source_health(subscription_id: str, source_name: str, count: int) -> None:
    """Upsert source health. Increments consecutive_empty when count=0."""
    now = _now()
    with _conn() as con:
        existing = con.execute(
            "SELECT id, consecutive_empty FROM source_health WHERE subscription_id=? AND source_name=?",
            (subscription_id, source_name),
        ).fetchone()
        if existing:
            consecutive_empty = (existing["consecutive_empty"] + 1) if count == 0 else 0
            con.execute(
                """UPDATE source_health
                   SET last_run_at=?, last_count=?, consecutive_empty=?
                   WHERE id=?""",
                (now, count, consecutive_empty, existing["id"]),
            )
        else:
            con.execute(
                """INSERT INTO source_health
                   (id, subscription_id, source_name, last_run_at, last_count,
                    consecutive_empty, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), subscription_id, source_name, now, count,
                    1 if count == 0 else 0, now,
                ),
            )


def get_source_health(subscription_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM source_health WHERE subscription_id=? ORDER BY source_name",
            (subscription_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_quiet_sources(threshold: int = 3) -> list[dict]:
    """Sources with consecutive_empty >= threshold across all subscriptions."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM source_health WHERE consecutive_empty >= ? ORDER BY consecutive_empty DESC",
            (threshold,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Scheduled runs ────────────────────────────────────────────────────────────

def schedule_run(subscription_id: str, scheduled_at: str) -> dict:
    run_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            """INSERT INTO scheduled_runs
               (id, subscription_id, scheduled_at, status, run_id, created_at)
               VALUES (?,?,?,'pending',NULL,?)""",
            (run_id, subscription_id, scheduled_at, now),
        )
    return {
        "id": run_id,
        "subscription_id": subscription_id,
        "scheduled_at": scheduled_at,
        "status": "pending",
        "run_id": None,
        "created_at": now,
    }


def claim_scheduled_run(scheduled_run_id: str) -> bool:
    """Mark as 'running'. Returns False if already running/done."""
    with _conn() as con:
        cur = con.execute(
            """UPDATE scheduled_runs SET status='running'
               WHERE id=? AND status='pending'""",
            (scheduled_run_id,),
        )
    return cur.rowcount > 0


def complete_scheduled_run(
    scheduled_run_id: str, run_id: str, status: str = "done"
) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE scheduled_runs SET status=?, run_id=? WHERE id=?",
            (status, run_id, scheduled_run_id),
        )


def list_scheduled_runs(subscription_id: str, limit: int = 20) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM scheduled_runs WHERE subscription_id=?
               ORDER BY scheduled_at DESC LIMIT ?""",
            (subscription_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Lead feedback ─────────────────────────────────────────────────────────────

def add_lead_feedback(lead_id: str, reason: str, note: str | None = None) -> dict:
    fb_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO lead_feedback (id, lead_id, reason, note, created_at) VALUES (?,?,?,?,?)",
            (fb_id, lead_id, reason, note, now),
        )
    return {"id": fb_id, "lead_id": lead_id, "reason": reason, "note": note, "created_at": now}


def list_lead_feedback(lead_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM lead_feedback WHERE lead_id=? ORDER BY created_at DESC",
            (lead_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_rejection_reasons(subscription_id: str, days: int = 30) -> list[dict]:
    """Aggregated rejection reasons with counts. For the results page."""
    with _conn() as con:
        rows = con.execute(
            """SELECT lf.reason, COUNT(*) as count
               FROM lead_feedback lf
               JOIN leads l ON l.id = lf.lead_id
               WHERE l.subscription_id=?
                 AND lf.created_at >= datetime('now', ?)
               GROUP BY lf.reason
               ORDER BY count DESC""",
            (subscription_id, f"-{days} days"),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Spend tracking ────────────────────────────────────────────────────────────

def get_subscription_spend_today(subscription_id: str) -> float:
    """Sum of cost_usd from llm_calls for runs in this subscription today."""
    with _conn() as con:
        row = con.execute(
            """SELECT COALESCE(SUM(lc.cost_usd), 0) as total
               FROM llm_calls lc
               JOIN runs r ON r.id = lc.run_id
               WHERE r.subscription_id=?
                 AND date(lc.created_at) = date('now')""",
            (subscription_id,),
        ).fetchone()
    return float(row["total"]) if row else 0.0


# ── Results / analytics ───────────────────────────────────────────────────────

def get_reply_rates_by_score_band(subscription_id: str, days: int = 30) -> list[dict]:
    """Returns [{score_band, total, replied, rate}] for score buckets 0-50,50-60,60-70,70-80,80-90,90+."""
    with _conn() as con:
        rows = con.execute(
            """SELECT scored_json, status FROM leads
               WHERE subscription_id=?
                 AND created_at >= datetime('now', ?)""",
            (subscription_id, f"-{days} days"),
        ).fetchall()

    bands: dict[str, dict] = {
        "0-50": {"score_band": "0-50", "total": 0, "replied": 0},
        "50-60": {"score_band": "50-60", "total": 0, "replied": 0},
        "60-70": {"score_band": "60-70", "total": 0, "replied": 0},
        "70-80": {"score_band": "70-80", "total": 0, "replied": 0},
        "80-90": {"score_band": "80-90", "total": 0, "replied": 0},
        "90+": {"score_band": "90+", "total": 0, "replied": 0},
    }
    for r in rows:
        try:
            scored = json.loads(r["scored_json"])
            score = scored.get("score", 0) or 0
        except Exception:
            score = 0
        if score < 50:
            band = "0-50"
        elif score < 60:
            band = "50-60"
        elif score < 70:
            band = "60-70"
        elif score < 80:
            band = "70-80"
        elif score < 90:
            band = "80-90"
        else:
            band = "90+"
        bands[band]["total"] += 1
        if r["status"] == "replied":
            bands[band]["replied"] += 1

    result = []
    for b in bands.values():
        b["rate"] = round(b["replied"] / b["total"], 3) if b["total"] else None
        result.append(b)
    return result


def get_subscription_stats(subscription_id: str, days: int = 30) -> dict:
    with _conn() as con:
        status_rows = con.execute(
            """SELECT status, COUNT(*) as n FROM leads
               WHERE subscription_id=? AND created_at >= datetime('now', ?)
               GROUP BY status""",
            (subscription_id, f"-{days} days"),
        ).fetchall()
        cost_row = con.execute(
            """SELECT COALESCE(SUM(lc.cost_usd), 0) as total_cost, COUNT(*) as calls
               FROM llm_calls lc
               JOIN runs r ON r.id = lc.run_id
               WHERE r.subscription_id=? AND lc.created_at >= datetime('now', ?)""",
            (subscription_id, f"-{days} days"),
        ).fetchone()
        run_row = con.execute(
            """SELECT COUNT(*) as run_count FROM runs
               WHERE subscription_id=? AND started_at >= datetime('now', ?)""",
            (subscription_id, f"-{days} days"),
        ).fetchone()

    status_counts = {r["status"]: r["n"] for r in status_rows}
    total_leads = sum(status_counts.values())
    replied = status_counts.get("replied", 0)
    contacted = status_counts.get("sent", 0) + replied

    return {
        "subscription_id": subscription_id,
        "days": days,
        "leads": status_counts,
        "total_leads": total_leads,
        "reply_rate": round(replied / contacted, 3) if contacted else None,
        "llm_cost_usd": round(float(cost_row["total_cost"]), 4),
        "llm_calls": cost_row["calls"] or 0,
        "run_count": run_row["run_count"] if run_row else 0,
    }
