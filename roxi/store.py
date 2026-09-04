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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

_DB_PATH = os.environ.get("ROXI_DB_PATH", "roxi.db")


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(path: str | None = None) -> None:
    global _DB_PATH
    if path:
        _DB_PATH = path
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                vertical_id TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                signal_json TEXT NOT NULL,
                scored_json TEXT NOT NULL,
                research_json TEXT,
                draft_json TEXT,
                dedupe_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dedupe_keys (
                key TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
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
                total_cost_usd REAL DEFAULT 0
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
        """)
    log.debug("init_db complete: %s", _DB_PATH)


def save(lead: Lead, vertical_id: str) -> None:
    try:
      _save(lead, vertical_id)
    except Exception as exc:
        log.error("store.save failed for lead %s: %s", lead.id, exc, exc_info=True)
        raise


def _save(lead: Lead, vertical_id: str) -> None:
    with _conn() as con:
        con.execute(
            """INSERT OR IGNORE INTO leads
               (id, vertical_id, raw_json, signal_json, scored_json,
                research_json, draft_json, dedupe_key, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                lead.id,
                vertical_id,
                lead.raw.model_dump_json(),
                lead.signal.model_dump_json(),
                lead.scored.model_dump_json(),
                lead.research.model_dump_json() if lead.research else None,
                lead.draft.model_dump_json() if lead.draft else None,
                lead.dedupe_key,
                lead.status,
                lead.created_at.isoformat(),
            ),
        )
        con.execute(
            "INSERT OR IGNORE INTO dedupe_keys (key, created_at) VALUES (?,?)",
            (lead.dedupe_key, lead.created_at.isoformat()),
        )


def update_status(lead_id: str, status: str) -> None:
    try:
        with _conn() as con:
            con.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
    except Exception as exc:
        log.error("store.update_status failed for lead %s → %s: %s", lead_id, status, exc, exc_info=True)
        raise


def get_lead(lead_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
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
        deleted = cur.rowcount > 0  # read before connection closes
    return deleted


def pending_leads(vertical_id: str) -> list[Lead]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM leads WHERE vertical_id=? AND status='pending'",
            (vertical_id,),
        ).fetchall()
    return [_row_to_lead(r) for r in rows]


def recent_company_names(days: int = 30) -> list[str]:
    with _conn() as con:
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


def seen_dedupe_keys() -> set[str]:
    with _conn() as con:
        rows = con.execute("SELECT key FROM dedupe_keys").fetchall()
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


def start_run(vertical_id: str, org_id: str | None = None) -> str:
    log.debug("store.start_run: vertical=%s org=%s", vertical_id, org_id)
    run_id = str(uuid.uuid4())
    try:
        with _conn() as con:
            con.execute(
                """INSERT INTO runs (id, vertical_id, org_id, started_at)
                   VALUES (?,?,?,?)""",
                (run_id, vertical_id, org_id, _now()),
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
        created_at=row["created_at"],
    )
