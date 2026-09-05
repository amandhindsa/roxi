"""
Telemetry helpers.

Thin wrappers so every agent/collector/dispatcher can emit structured
pipeline events without importing store directly. Events go into the
`events` table (created on first write) and are surfaced by the
/api/telemetry endpoint.

Usage:
    from roxi.telemetry import emit

    emit("collector.run", vertical_id="hauler_ai", run_id=run_id,
         data={"source": "job_boards", "items": 42})
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

log = logging.getLogger(__name__)


def emit(
    event: str,
    *,
    run_id: str | None = None,
    org_id: str | None = None,
    vertical_id: str | None = None,
    agent: str | None = None,
    lead_id: str | None = None,
    data: dict[str, Any] | None = None,
    level: str = "info",
) -> None:
    """
    Write one structured event. Fails silently — telemetry must never crash
    the pipeline.
    """
    try:
        _write(
            event=event,
            run_id=run_id,
            org_id=org_id,
            vertical_id=vertical_id,
            agent=agent,
            lead_id=lead_id,
            data=data or {},
            level=level,
        )
    except Exception as exc:
        log.warning("telemetry.emit failed: %s", exc)


def _write(
    event: str,
    run_id: str | None,
    org_id: str | None,
    vertical_id: str | None,
    agent: str | None,
    lead_id: str | None,
    data: dict,
    level: str,
) -> None:
    import os, datetime as _dt
    ts = _dt.datetime.now(_dt.timezone.utc).isoformat()

    if os.environ.get("USE_SUPABASE") == "1":
        from roxi.store_supabase import _get_client
        _get_client().table("events").insert({
            "id": str(uuid.uuid4()),
            "event": event,
            "level": level,
            "run_id": run_id,
            "org_id": org_id,
            "vertical_id": vertical_id,
            "agent": agent,
            "lead_id": lead_id,
            "data_json": json.dumps(data),
            "created_at": ts,
        }).execute()
    else:
        from roxi.store import _conn, _now
        ts = _now()
        with _conn() as con:
            con.execute(
                """INSERT INTO events
                   (id, event, level, run_id, org_id, vertical_id, agent, lead_id, data_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    event,
                    level,
                    run_id,
                    org_id,
                    vertical_id,
                    agent,
                    lead_id,
                    json.dumps(data),
                    ts,
                ),
            )
