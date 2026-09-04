"""
Phase 5 — scoring retune from outcome evidence.

Reads sent/replied leads from the store, computes reply rate per score band and
per rule, then prints a recommended YAML diff for the vertical's scoring_rules.

Run after Phase 4 produces ≥30 sent leads with outcome data.

Usage:
  python scripts/retune.py [vertical] [--days N] [--min-sent N]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from roxi import store
from roxi.config import load_vertical


def retune(vertical_id: str, days: int = 90, min_sent: int = 30) -> None:
    store.init_db()

    with store._conn() as con:
        rows = con.execute(
            """SELECT scored_json, status FROM leads
               WHERE vertical_id = ?
               AND status IN ('sent', 'replied')
               AND created_at >= datetime('now', ?)""",
            (vertical_id, f"-{days} days"),
        ).fetchall()

    leads = []
    for r in rows:
        try:
            scored = json.loads(r["scored_json"])
            leads.append({"score": scored["score"], "rules_fired": scored.get("rules_fired", []), "replied": r["status"] == "replied"})
        except Exception:
            pass

    if len(leads) < min_sent:
        print(f"Only {len(leads)} sent leads — need ≥{min_sent} for reliable retune. Collect more data first.")
        return

    sent = len(leads)
    replied = sum(1 for l in leads if l["replied"])
    overall_reply_rate = replied / sent

    print(f"Retune analysis — {vertical_id} — {sent} sent leads, {overall_reply_rate:.1%} overall reply rate")
    print()

    # Score band analysis
    print("Score-band performance:")
    print(f"  {'Band':<10} {'Sent':>6} {'Replied':>8} {'Rate':>8} {'vs overall':>12}")
    for lo, hi in [(70, 80), (80, 90), (90, 101)]:
        band_leads = [l for l in leads if lo <= l["score"] < hi]
        b_sent = len(band_leads)
        b_replied = sum(1 for l in band_leads if l["replied"])
        rate = b_replied / b_sent if b_sent else 0
        delta = rate - overall_reply_rate
        sign = "+" if delta >= 0 else ""
        print(f"  {f'{lo}-{hi-1}':<10} {b_sent:>6} {b_replied:>8} {rate:>7.1%} {sign}{delta:>10.1%}")

    print()

    # Rule performance
    rule_stats: dict[str, dict] = {}
    for lead in leads:
        rules_in_this_lead = {r["rule"] for r in lead["rules_fired"]}
        for rule in rules_in_this_lead:
            if rule not in rule_stats:
                rule_stats[rule] = {"sent": 0, "replied": 0}
            rule_stats[rule]["sent"] += 1
            if lead["replied"]:
                rule_stats[rule]["replied"] += 1

    if rule_stats:
        print("Rule-level performance (how leads with each rule fired perform):")
        print(f"  {'Rule':<55} {'Sent':>6} {'Rate':>8} {'vs baseline':>12}")
        for rule, stats in sorted(rule_stats.items(), key=lambda kv: kv[1]["replied"] / kv[1]["sent"] if kv[1]["sent"] else 0, reverse=True):
            s = stats["sent"]
            r = stats["replied"]
            rate = r / s if s else 0
            delta = rate - overall_reply_rate
            sign = "+" if delta >= 0 else ""
            truncated = rule[:52] + "..." if len(rule) > 55 else rule
            print(f"  {truncated:<55} {s:>6} {rate:>7.1%} {sign}{delta:>10.1%}")

    print()
    print("Recommendations:")

    # Find rules with rate > 1.5x baseline (consider raising delta)
    good_rules = [(r, s) for r, s in rule_stats.items()
                  if s["sent"] >= 5 and s["replied"] / s["sent"] > 1.5 * overall_reply_rate]
    for rule, stats in good_rules:
        rate = stats["replied"] / stats["sent"]
        print(f"  ↑ Consider raising delta for: \"{rule}\"")
        print(f"    ({rate:.0%} reply rate vs {overall_reply_rate:.0%} baseline on {stats['sent']} sends)")

    # Find rules with rate < 0.5x baseline (consider lowering delta)
    bad_rules = [(r, s) for r, s in rule_stats.items()
                 if s["sent"] >= 5 and s["replied"] / s["sent"] < 0.5 * overall_reply_rate]
    for rule, stats in bad_rules:
        rate = stats["replied"] / stats["sent"]
        print(f"  ↓ Consider lowering delta for: \"{rule}\"")
        print(f"    ({rate:.0%} reply rate vs {overall_reply_rate:.0%} baseline on {stats['sent']} sends)")

    # Threshold check
    band_70_79 = [l for l in leads if 70 <= l["score"] < 80]
    if band_70_79:
        low_band_rate = sum(1 for l in band_70_79 if l["replied"]) / len(band_70_79)
        if low_band_rate < 0.5 * overall_reply_rate:
            print(f"  ↑ Consider raising qualify_threshold from 70 to 80")
            print(f"    (70-79 band: {low_band_rate:.0%} reply rate vs {overall_reply_rate:.0%} overall)")

    if not good_rules and not bad_rules:
        print("  No clear retune signals — rules are performing consistently.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("vertical", nargs="?", default="hauler_ai")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--min-sent", type=int, default=30)
    args = p.parse_args()
    retune(args.vertical, days=args.days, min_sent=args.min_sent)
