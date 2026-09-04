"""
Phase 5 — migrate SQLite data to Supabase.

Reads all rows from roxi.db and upserts them into Supabase.
Safe to run multiple times (uses upsert with on_conflict=dedupe_key).

Usage:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/migrate_to_supabase.py [--db roxi.db]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def migrate(db_path: str) -> None:
    from supabase import create_client
    import os

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    sb = create_client(url, key)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # Migrate leads
    leads = con.execute("SELECT * FROM leads").fetchall()
    print(f"Migrating {len(leads)} leads…")
    for batch_start in range(0, len(leads), 50):
        batch = leads[batch_start:batch_start + 50]
        rows = [dict(r) for r in batch]
        sb.table("leads").upsert(rows, on_conflict="dedupe_key", ignore_duplicates=True).execute()
        print(f"  {min(batch_start + 50, len(leads))}/{len(leads)}")

    # Migrate dedupe_keys
    keys = con.execute("SELECT * FROM dedupe_keys").fetchall()
    print(f"Migrating {len(keys)} dedupe keys…")
    for batch_start in range(0, len(keys), 200):
        batch = keys[batch_start:batch_start + 200]
        rows = [dict(r) for r in batch]
        sb.table("dedupe_keys").upsert(rows, on_conflict="key", ignore_duplicates=True).execute()

    # Migrate llm_calls
    calls = con.execute("SELECT * FROM llm_calls").fetchall()
    print(f"Migrating {len(calls)} LLM call logs…")
    for batch_start in range(0, len(calls), 200):
        batch = calls[batch_start:batch_start + 200]
        rows = [dict(r) for r in batch]
        sb.table("llm_calls").upsert(rows, on_conflict="id", ignore_duplicates=True).execute()

    con.close()
    print("Migration complete.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="roxi.db")
    args = p.parse_args()
    migrate(args.db)
