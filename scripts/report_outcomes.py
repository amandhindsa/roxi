"""
Phase 4 — reply-rate report.

Prints a summary of lead outcomes for a vertical over a time window.
Run via:  python -m roxi report [vertical] [--days N]
      or: python scripts/report_outcomes.py [vertical] [--days N]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from roxi import store


def print_report(vertical_id: str, days: int = 30) -> None:
    with store._conn() as con:
        rows = con.execute(
            """SELECT status, COUNT(*) as n FROM leads
               WHERE vertical_id = ?
               AND created_at >= datetime('now', ?)
               GROUP BY status""",
            (vertical_id, f"-{days} days"),
        ).fetchall()

        score_rows = con.execute(
            """SELECT scored_json FROM leads
               WHERE vertical_id = ?
               AND created_at >= datetime('now', ?)""",
            (vertical_id, f"-{days} days"),
        ).fetchall()

        cost_row = con.execute(
            """SELECT SUM(cost_usd) as total_cost, SUM(input_tokens) as in_tok,
               SUM(output_tokens) as out_tok
               FROM llm_calls
               WHERE created_at >= datetime('now', ?)""",
            (f"-{days} days",),
        ).fetchone()

    import json
    scores = []
    for r in score_rows:
        try:
            scores.append(json.loads(r["scored_json"])["score"])
        except Exception:
            pass

    status = {r["status"]: r["n"] for r in rows}
    total = sum(status.values())
    approved = status.get("approved", 0)
    rejected = status.get("rejected", 0)
    sent = status.get("sent", 0) + status.get("replied", 0)
    replied = status.get("replied", 0)

    approval_rate = approved / (approved + rejected) if (approved + rejected) else None
    reply_rate = replied / sent if sent else None
    avg_score = sum(scores) / len(scores) if scores else None

    sep = "─" * 56
    print(sep)
    print(f"Roxi outcomes — {vertical_id} — last {days} days")
    print(sep)
    print(f"  Total leads generated:  {total}")
    print(f"  Pending:                {status.get('pending', 0)}")
    print(f"  Approved:               {approved}")
    print(f"  Rejected:               {rejected}")
    print(f"  Sent:                   {sent}")
    print(f"  Replied:                {replied}")
    print()
    if approval_rate is not None:
        flag = " ✓" if approval_rate >= 0.60 else " ✗ (target ≥60%)"
        print(f"  Approval rate:          {approval_rate:.0%}{flag}")
    if reply_rate is not None:
        flag = " ✓" if reply_rate >= 0.08 else " ✗ (target ≥8%)"
        print(f"  Reply rate:             {reply_rate:.1%}{flag}")
    if avg_score is not None:
        print(f"  Avg score (qualified):  {avg_score:.1f}/100")
    print()
    cost = cost_row["total_cost"] or 0
    print(f"  LLM cost (last {days}d):    ${cost:.2f}")
    print(sep)

    if reply_rate is not None and reply_rate < 0.08 and sent >= 10:
        print()
        print("  ⚠  Reply rate below 8% threshold on ≥10 sends.")
        print("     Per kill criteria: stop adding channels and reconsider the 'why now'.")


def _score_band_breakdown(vertical_id: str, days: int) -> None:
    import json
    with store._conn() as con:
        rows = con.execute(
            """SELECT scored_json, status FROM leads
               WHERE vertical_id = ?
               AND status IN ('sent', 'replied')
               AND created_at >= datetime('now', ?)""",
            (vertical_id, f"-{days} days"),
        ).fetchall()

    bands: dict[str, dict] = {
        "70-79": {"sent": 0, "replied": 0},
        "80-89": {"sent": 0, "replied": 0},
        "90-100": {"sent": 0, "replied": 0},
    }

    for r in rows:
        try:
            score = json.loads(r["scored_json"])["score"]
            status = r["status"]
        except Exception:
            continue

        if 70 <= score < 80:
            band = "70-79"
        elif 80 <= score < 90:
            band = "80-89"
        elif score >= 90:
            band = "90-100"
        else:
            continue

        bands[band]["sent"] += 1
        if status == "replied":
            bands[band]["replied"] += 1

    print("\n  Score-band breakdown:")
    print(f"  {'Band':<10} {'Sent':>6} {'Replied':>8} {'Reply %':>8}")
    for band, counts in bands.items():
        s, r = counts["sent"], counts["replied"]
        pct = f"{r/s:.0%}" if s else "—"
        print(f"  {band:<10} {s:>6} {r:>8} {pct:>8}")


if __name__ == "__main__":
    import argparse
    store.init_db()
    p = argparse.ArgumentParser()
    p.add_argument("vertical", nargs="?", default="hauler_ai")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()
    print_report(args.vertical, args.days)
    _score_band_breakdown(args.vertical, args.days)
