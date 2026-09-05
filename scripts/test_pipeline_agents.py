"""
Seed test: inject real Canadian carrier companies directly into the pipeline
and run extract -> score -> research -> draft so we can see each agent's output.

Usage:
    USE_SUPABASE=1 SUPABASE_URL=... SUPABASE_SERVICE_KEY=... ANTHROPIC_API_KEY=... \
      python scripts/test_pipeline_agents.py
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from roxi.logging_config import configure as _configure_logging
_configure_logging(level="WARNING")  # suppress noisy logs, we print our own
log = logging.getLogger("test.pipeline")

from roxi.config import load_vertical
from roxi.models import RawItem
from roxi.agents.extractor import extract
from roxi.agents.scorer import score
from roxi.agents.researcher import research_company
from roxi.agents.drafter import draft_email
from roxi import store

SEED_ITEMS = [
    RawItem(
        channel="job_boards",
        source_url="https://ca.indeed.com/viewjob?jk=seed1",
        title="Dispatcher - Growing Cross-Border Carrier",
        body=(
            "Rocky Mountain Freight Ltd. (Langley, BC) is hiring a full-time dispatcher "
            "to manage our fleet of 22 flatbeds doing daily US-Canada runs. "
            "We recently received our MC authority and are expanding our reefer division. "
            "Owner is hands-on and looking for someone to help streamline our eManifest filings."
        ),
        fetched_at="2026-09-05T00:00:00+00:00",
    ),
    RawItem(
        channel="job_boards",
        source_url="https://ca.indeed.com/viewjob?jk=seed2",
        title="Safety & Compliance Officer - Trucking - Edmonton AB",
        body=(
            "Prairie Winds Transport Inc. (Edmonton, AB) - 35 power units, cross-border dry van. "
            "Hiring safety officer to handle CBSA eManifest submissions and carrier compliance. "
            "We currently use paper-based customs prep and want to modernize. "
            "Fleet manager Michael Johnson is overseeing the hire."
        ),
        fetched_at="2026-09-05T00:00:00+00:00",
    ),
    RawItem(
        channel="job_boards",
        source_url="https://ca.indeed.com/viewjob?jk=seed3",
        title="Fleet Manager - 15 Trucks - Windsor ON",
        body=(
            "Maple Leaf Carriers (Windsor, ON) - small family-owned carrier, 15 semis, "
            "running produce loads between Ontario and Michigan daily. "
            "Owner: 'we are drowning in eManifest paperwork, need help managing it.' "
            "Looking for fleet manager to also oversee border crossing logistics."
        ),
        fetched_at="2026-09-05T00:00:00+00:00",
    ),
    RawItem(
        channel="job_boards",
        source_url="https://ca.indeed.com/viewjob?jk=seed4",
        title="Owner-Operator - Single Truck for Hire",
        body=(
            "Independent owner-operator Dave looking for loads. Runs his own Peterbilt 579, "
            "mainly local BC hauls. Not interested in cross-border, no employees."
        ),
        fetched_at="2026-09-05T00:00:00+00:00",
    ),
    RawItem(
        channel="job_boards",
        source_url="https://ca.indeed.com/viewjob?jk=seed5",
        title="Customs Coordinator - New MC Authority - Mississauga ON",
        body=(
            "Northern Star Logistics (Mississauga, ON) just received our new MC authority "
            "last month. 18-truck fleet hauling auto parts Windsor-Detroit corridor. "
            "Urgently hiring a customs coordinator - we have been struggling with manual "
            "eManifest entry and made 3 border delays this quarter."
        ),
        fetched_at="2026-09-05T00:00:00+00:00",
    ),
]


def sep(label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print("="*60)


def main():
    vertical = load_vertical("verticals/hauler_ai.yaml")
    store.init_db()

    sep(f"Pipeline agent test  --  {len(SEED_ITEMS)} seed companies")

    # Stage 1: Extractor
    print("\nSTAGE 1 - EXTRACTOR\n")
    signals = []
    for item in SEED_ITEMS:
        try:
            sig = extract(item, vertical)
            if sig:
                signals.append(sig)
                print(f"  OK  {sig.company}  |  fleet={sig.fleet_size}  |  type={sig.signal_type}")
            else:
                print(f"  --  (no signal extracted)  {item.title[:50]}")
        except Exception as exc:
            print(f"  ERR {item.title[:50]}  --  {exc}")

    print(f"\n  -> {len(signals)} / {len(SEED_ITEMS)} signals extracted")

    # Stage 2: Scorer
    print("\nSTAGE 2 - SCORER\n")
    scored = []
    for sig in signals:
        try:
            result = score(sig, vertical)
            if result:
                tag = "QUALIFIED" if result.score >= vertical.qualify_threshold else "low score"
                print(f"  {tag:10s}  {result.company_name}  |  score={result.score}")
                print(f"             reason: {result.reason[:100]}")
            else:
                print(f"  DISQUALIFIED  {sig.company}")
            if result:
                scored.append(result)
        except Exception as exc:
            print(f"  ERR  {sig.company}  --  {exc}")

    qualified = [s for s in scored if s.score >= vertical.qualify_threshold]
    print(f"\n  -> {len(qualified)} qualified (threshold={vertical.qualify_threshold})")

    # Stage 3: Researcher
    print("\nSTAGE 3 - RESEARCHER\n")
    leads = []
    for sig in qualified:
        try:
            lead = research_company(sig, vertical)
            if lead:
                leads.append(lead)
                print(f"  OK  {lead.company_name}")
                print(f"      contact : {lead.contact_name or 'unknown'}  <{lead.contact_email or 'no email found'}>")
                print(f"      summary : {(lead.research_summary or '')[:140]}")
                print()
        except Exception as exc:
            print(f"  ERR  {sig.company_name}  --  {exc}")

    print(f"  -> {len(leads)} leads researched")

    # Stage 4: Drafter
    print("\nSTAGE 4 - DRAFTER\n")
    for lead in leads:
        try:
            drafted = draft_email(lead, vertical)
            print(f"  OK  {drafted.company_name}")
            print(f"      Subject : {drafted.subject_line}")
            body_preview = (drafted.body or "")[:300].replace("\n", " ")
            print(f"      Body    : {body_preview}...")
            print()
        except Exception as exc:
            print(f"  ERR  {lead.company_name}  --  {exc}")

    sep(f"Done  --  {len(leads)} leads ready for approval in the UI")


if __name__ == "__main__":
    main()
