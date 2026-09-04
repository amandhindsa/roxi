#!/usr/bin/env python3
"""
Eval harness for Roxi scoring agents.

Runs all 50 fixtures through Extractor + Scorer, reports:
  - Mean absolute error (MAE) on non-disqualified items
  - Disqualifier recall (fraction of expected disqualifiers caught)
  - False-positive rate (items above threshold that should be disqualified)

Exit criteria (Phase 0): MAE <= 12, disqualifier recall == 1.0
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from roxi.agents.extractor import extract
from roxi.agents.scorer import score
from roxi.config import load_vertical
from roxi.models import RawItem
from roxi import store

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "hauler_ai.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"
VERTICAL_PATH = Path(__file__).parent.parent / "verticals" / "hauler_ai.yaml"
QUALIFY_THRESHOLD = 70
EXIT_MAE = 12.0

store.init_db(":memory:")


def load_fixtures() -> list[dict]:
    fixtures = []
    for line in FIXTURES_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            fixtures.append(json.loads(line))
    return fixtures


def run_fixture(fixture: dict, vertical) -> dict:
    raw = RawItem.model_validate(fixture["raw"])
    expected_score = fixture["expected_score"]
    expected_disq = fixture.get("expected_disqualifier")

    signal = extract(raw, vertical)

    if signal is None:
        return {
            "company": fixture["raw"].get("title", "unknown"),
            "expected_score": expected_score,
            "expected_disqualifier": expected_disq,
            "actual_score": 0,
            "actual_disqualifier": None,
            "extracted": False,
            "error": "extractor returned None (not identifiable)",
            "notes": fixture.get("notes", ""),
        }

    scored = score(signal, vertical)

    return {
        "company": signal.company,
        "expected_score": expected_score,
        "expected_disqualifier": expected_disq,
        "actual_score": scored.score,
        "actual_disqualifier": scored.disqualified_by,
        "extracted": True,
        "rules_fired": [r.model_dump() for r in scored.rules_fired],
        "reasoning": scored.reasoning,
        "notes": fixture.get("notes", ""),
    }


def compute_metrics(results: list[dict]) -> dict:
    scorable = [
        r for r in results
        if r.get("extracted") and r["expected_disqualifier"] is None and r["actual_disqualifier"] is None
    ]
    expected_disq = [r for r in results if r["expected_disqualifier"] is not None]
    actual_disq_on_expected = [
        r for r in expected_disq if r.get("actual_disqualifier") is not None
    ]

    false_positives = [
        r for r in results
        if r.get("extracted")
        and r["expected_disqualifier"] is not None
        and r["actual_score"] >= QUALIFY_THRESHOLD
    ]

    mae = None
    if scorable:
        errors = [abs(r["expected_score"] - r["actual_score"]) for r in scorable]
        mae = sum(errors) / len(errors)

    disq_recall = None
    if expected_disq:
        disq_recall = len(actual_disq_on_expected) / len(expected_disq)

    fp_rate = None
    if expected_disq:
        fp_rate = len(false_positives) / len(expected_disq)

    return {
        "total": len(results),
        "extracted": sum(1 for r in results if r.get("extracted")),
        "scorable_count": len(scorable),
        "mae": round(mae, 2) if mae is not None else None,
        "disqualifier_recall": round(disq_recall, 3) if disq_recall is not None else None,
        "false_positive_rate": round(fp_rate, 3) if fp_rate is not None else None,
        "expected_disqualifiers": len(expected_disq),
        "caught_disqualifiers": len(actual_disq_on_expected),
        "exit_criteria_met": (
            mae is not None and mae <= EXIT_MAE
            and disq_recall is not None and disq_recall == 1.0
        ),
    }


def print_report(metrics: dict, results: list[dict]) -> None:
    sep = "─" * 60
    print(sep)
    print("Roxi eval — hauler_ai vertical")
    print(sep)
    print(f"  Total fixtures:       {metrics['total']}")
    print(f"  Extracted:            {metrics['extracted']}")
    print(f"  Scorable (no disq):   {metrics['scorable_count']}")
    print()
    mae = metrics["mae"]
    mae_flag = " ✓" if mae is not None and mae <= EXIT_MAE else " ✗"
    print(f"  MAE:                  {mae}{mae_flag}  (exit ≤{EXIT_MAE})")

    disq_r = metrics["disqualifier_recall"]
    disq_flag = " ✓" if disq_r == 1.0 else " ✗"
    print(f"  Disqualifier recall:  {disq_r}{disq_flag}  (exit = 1.0)")
    print(f"  False-positive rate:  {metrics['false_positive_rate']}")
    print()
    if metrics["exit_criteria_met"]:
        print("  ✓ EXIT CRITERIA MET — ready for Phase 1")
    else:
        print("  ✗ exit criteria not yet met")
    print(sep)

    misses = [
        r for r in results
        if r.get("extracted")
        and r["expected_disqualifier"] is None
        and abs(r["expected_score"] - r["actual_score"]) > EXIT_MAE
    ]
    if misses:
        print("\nLargest scoring misses:")
        misses.sort(key=lambda r: abs(r["expected_score"] - r["actual_score"]), reverse=True)
        for r in misses[:10]:
            delta = r["actual_score"] - r["expected_score"]
            sign = "+" if delta >= 0 else ""
            print(f"  {r['company'][:40]:<40}  expected={r['expected_score']:3d}  actual={r['actual_score']:3d}  ({sign}{delta})")

    missed_disq = [
        r for r in results
        if r.get("expected_disqualifier") and not r.get("actual_disqualifier")
    ]
    if missed_disq:
        print("\nMissed disqualifiers (expected disqualification, not caught):")
        for r in missed_disq:
            print(f"  {r['company'][:40]:<40}  expected: {r['expected_disqualifier']}")


def main() -> None:
    vertical = load_vertical(VERTICAL_PATH)
    fixtures = load_fixtures()

    print(f"Running {len(fixtures)} fixtures…")
    results = []
    for i, fixture in enumerate(fixtures, 1):
        print(f"  [{i:2d}/{len(fixtures)}] {fixture['raw'].get('title', '')[:60]}", end="\r")
        result = run_fixture(fixture, vertical)
        results.append(result)
    print()

    metrics = compute_metrics(results)
    print_report(metrics, results)

    RESULTS_DIR.mkdir(exist_ok=True)
    run_file = RESULTS_DIR / f"{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')}.json"
    run_file.write_text(json.dumps({"metrics": metrics, "results": results}, indent=2))
    print(f"\nResults saved to {run_file}")

    if not metrics["exit_criteria_met"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
