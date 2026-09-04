# Roxi — known bugs and code review

Review of `roxi/` as of 4 September 2026. Files read: `pipeline.py`, `llm.py`, `config.py`,
`store.py`, `dedupe.py`, `dispatcher.py`, `agents/extractor.py`, `agents/scorer.py`,
`agents/researcher.py`, `collectors/job_boards.py`.

Not yet reviewed: `agents/drafter.py` and `content/*` were reviewed in a later pass (see
`10-how-the-agents-work.html`); `api/app.py`, `collectors/reddit.py`, `collectors/registry.py`,
`telemetry.py`, `outcome.py`, `scripts/*`, and `approval-ui/*` remain unread.

**General assessment:** the structure is sound and unusually well instrumented for this stage.
Run IDs thread through every layer, `prompt_version` and `input_hash` are captured per call, and
collector failures degrade gracefully instead of killing the run. The bugs below are specific
defects, not architectural problems.

Severity: **CRITICAL** breaks the run · **HIGH** wrong output or real-world risk · **MEDIUM**
correctness or cost · **LOW** hygiene.

---

## CRITICAL

### C1. Model IDs are stale — every Sonnet and Opus call will fail

`roxi/llm.py`
```python
SONNET = "claude-sonnet-4-6"     # not a current model ID
OPUS   = "claude-opus-4-8"       # not a current model ID
```

Current API strings are `claude-sonnet-5` and `claude-opus-5`. Haiku (`claude-haiku-4-5-20251001`)
is correct.

The same stale values are duplicated in three more places:
- `roxi/config.py` → `ModelsConfig.researcher` and `.drafter` defaults
- `verticals/hauler_ai.yaml`
- `verticals/hvac_trades.yaml`

**Effect:** Researcher and Drafter raise `ExtractionError` on every call. Extractor and Scorer work,
so a run will collect, extract, score — and then produce zero leads, which reads like a scoring
problem rather than a config problem.

**Fix:** correct the constants in `llm.py`, then make `config.py` and the YAMLs import from them
rather than repeating literals. One source of truth. Verify current IDs against the Anthropic docs
before committing, since these change.

---

### C2. Job-board collector returns at most one item per query

`roxi/collectors/job_boards.py` → `_search_indeed`

```python
cards = page.query_selector_all("div.job_seen_beacon")[:20]
for card in cards:
    ...
    detail_text = _fetch_detail(page, source_url)   # navigates the SAME page
```

`_fetch_detail` calls `page.goto()` on the same page object the cards were selected from. That
navigation detaches every remaining card handle. On the next iteration `card.query_selector` throws
on a stale element, and the bare `except Exception: continue` swallows it silently.

**Effect:** card one yields an item, cards two through twenty fail invisibly. The run looks like a
thin day on the job boards rather than a broken scraper.

**Fix:** collect all `(title, company, href)` tuples into a list first, then fetch details — ideally
on a second page object so the search results stay live.

**Related:** the module comment says the browser is "initialised once per process via
`get_browser()`", but `fetch()` launches and closes a browser on every call. Comment and code
disagree; the code is the safer of the two, so fix the comment.

---

## HIGH

### H1. Dispatcher fabricates recipient email addresses

`roxi/dispatcher.py` → `_send_email`

```python
"email": f"contact@{lead.scored.company_domain}",
```

Two problems, one on top of the other.

First, `_send_one` guards with a comment that it "cannot send email to a fabricated address" —
and then `_send_email` fabricates exactly that. The guard checks that a *domain* exists, not that a
*verified address* does.

Second, `contact@` is a guess. Most will bounce, which damages the sending domain's reputation —
the same warmed `mail.sysbuddies.com`-style asset that took weeks to build. Under CASL, sending to
a guessed generic address also weakens any implied-consent argument, because implied consent
attaches to a *conspicuously published* business address, not to one you invented.

**Fix:** add a verified `contact_email` field to the lead, populated by enrichment or by the human
reviewer at approval time. If it is absent, the Dispatcher refuses to send. No guessing, ever.

---

### H2. Dedupe collapses unrelated companies

`roxi/dedupe.py` → `_fuzzy_match`

```python
if ca.split()[0] == cb.split()[0] and len(ca.split()[0]) >= 4:
    return True
```

`_CORP_SUFFIXES` strips `transport`, `transportation`, `trucking`, `logistics`, `freight`,
`carriers`, `express`, `lines`, `group`, `services`, `solutions`. So:

- "Pacific Freight" → `pacific`
- "Pacific Logistics" → `pacific`
- → merged, one of them silently dropped

In Canadian trucking, first-word collisions on Pacific, Northern, Western, Canadian, Prairie, and
Coastal are constant. The same applies to HVAC.

**Effect:** real leads dropped with no log line and no way to notice.

**Fix:** require the canonical name to have more than one token before trusting the first-token
rule, or drop that branch entirely and rely on the 0.82 `SequenceMatcher` ratio. Log every dedupe
collision with both names so collapses are auditable.

---

### H3. Dedupe runs before scoring, so the weaker signal can win

`roxi/pipeline.py`

Dedupe operates on raw `Signal` objects; `score()` runs afterwards. Whichever signal for a given
company appears first in the list claims that company's slot.

**Effect:** a low-value hiring post encountered first blocks a high-value authority filing for the
same carrier later in the same run. The pipeline then discards the better lead.

**Fix:** score first, then dedupe by company keeping the highest-scoring signal. Costs a few extra
Haiku calls per run — negligible against the research budget, and it is the cheap half of the
pipeline by design.

---

### H4. Cost table understates Haiku by ~25%

`roxi/llm.py`
```python
HAIKU: {"input": 0.80, "output": 4.00}
```

Claude Haiku 4.5 is **$1.00 / $5.00** per million tokens (verified against multiple public pricing
trackers, 4 September 2026). Sonnet at $3.00 / $15.00 matches Sonnet 4.x rates but should be
re-verified for the current Sonnet against Anthropic's official pricing page.

**Effect:** every figure in `llm_calls.cost_usd`, `runs.total_cost_usd`, `get_stats`, and
`daily_costs` is low. Per-org spend caps built on this data would be wrong in the permissive
direction.

**Fix:** correct the rates and add a comment with the verification date. Rates change; the table
needs an owner.

---

## MEDIUM

### M1. Researcher's web-search call has no `max_uses` cap

`roxi/agents/researcher.py`

```python
tools=[{"type": "web_search_20250305", "name": "web_search"}]
```

The system prompt asks for 2–3 searches, but nothing enforces it. A verbose run can execute many
more, and each is billed.

**Fix:** add `"max_uses": 4`. The daily research budget caps how many companies are researched, but
nothing currently caps cost *within* one research call.

---

### M2. `max_tokens=2048` is hard-coded for every call

`roxi/llm.py` → `structured()`

Fine for `Signal` and `ScoredSignal`. Tight for `ResearchBrief` with several hooks, and a
truncated response surfaces as a `ValidationError` and a wasted retry rather than as an obvious
length problem.

**Fix:** make it a `structured()` parameter with a sensible default.

---

### M3. Research search call logs an incomplete trace row

`roxi/agents/researcher.py` calls `store.log_llm_call` without `prompt_version`, `input_hash`, or
`outcome`, so those columns are null for the `researcher/search` agent.

**Effect:** the one call that cannot be replayed from the trace table is the one with the most
external variance. This defeats the purpose of the trace table for that stage.

**Fix:** pass all three, matching what `llm._log_call` does.

---

### M4. A lead can be delivered but not persisted

`roxi/store.py` → `_save` uses `INSERT OR IGNORE` on a table with `dedupe_key UNIQUE`. A collision
silently skips the write, while `pipeline.run` still appends the lead to its return list and
`deliver()` sends the card.

**Effect:** a Slack card exists for a lead with no database row, so approval will 404.

**Fix:** detect `rowcount == 0` and log a warning, or use `INSERT ... ON CONFLICT DO NOTHING
RETURNING id` and drop the lead from the delivered list when nothing was written.

---

### M5. Suppression keying is inconsistent

`roxi/dispatcher.py`
```python
contact_id = lead.scored.company_domain or lead.scored.company
```

The same company suppresses under its domain on one run and under its name on another, depending
on whether enrichment found a domain. A suppression added under one key will not match the other.

**Effect:** an unsubscribe can silently fail to suppress. This is the highest-consequence miss in
the system under CASL.

**Fix:** key suppression on a single canonical identifier — the verified contact email from H1 —
and never on a fallback.

---

### M6. `seen_dedupe_keys()` loads the entire table into memory

`roxi/store.py`. Every run reads all keys ever written, and `dedupe_keys` never expires. Fine now;
it grows without bound.

Note also the asymmetry: exact signal keys are permanent, while company matching uses a 30-day
window. Worth confirming that permanence is intended — it means an identical signal can never
resurface, even a year later when the company might be worth contacting again.

**Fix:** age out `dedupe_keys` on the same window as the company cooldown, or query by key instead
of loading the set.

---

## LOW

### L1. Empty `tests/` and empty `evals/results/`

The eval harness exists at `evals/run_evals.py` with fixtures at `evals/fixtures/hauler_ai.jsonl`,
but no results have been committed and `tests/` is empty.

Phase 0 exit criteria (MAE ≤ 12, disqualifier recall 100%) are therefore unverified, while
`compiler.py`, `responder.py`, `dispatcher.py`, the full `content/` pipeline, Supabase support, and
the Next.js approval UI are all built. That is phases 5–8 shipped ahead of phase 0.

This is not a code defect. It is the risk recorded in `05-roxi-implementation-plan.md`, now
observable in the repo. **Run the evals before tuning any prompt**, because without a baseline
there is no way to tell whether the fixes above improve or degrade scoring.

### L2. Indeed scraping is the most legally exposed component

`collectors/job_boards.py` scrapes Indeed, which their terms prohibit and which they block
aggressively. The 3-second delay and custom user agent help but do not change the terms position.

Prefer official job board APIs or the Government of Canada Job Bank, which publishes structured
data intended for reuse.

### L3. `roxi.db` sits in the repo root

Confirm it is covered by `.gitignore`. A committed SQLite file containing lead data would be a
privacy problem as well as a merge problem.

---

### M7. No stage-level observability — dropped items leave no trace

**Severity: MEDIUM as a defect, HIGH as a blocker on every other fix in this document.**

#### What exists

`llm_calls` records one row per model call: `model`, `agent`, `input_tokens`, `output_tokens`,
`cost_usd`, `latency_ms`, `outcome`, `prompt_version`, `input_hash`, `lead_id`, `run_id`, `org_id`.

`events` records pipeline milestones via `telemetry.emit`: `collector.run`, `collector.error`,
`run.start`, `run.finish`, `lead.created`, `lead.error`.

`runs` records per-run totals: `raw_collected`, `signals_extracted`, `signals_qualified`,
`leads_delivered`, `total_cost_usd`.

#### What is missing

**The data that moved between stages.** `input_hash` is `sha256(user)[:12]` — it proves two calls
had identical input and nothing more. It cannot be reversed, so the `Signal` that the Scorer
actually judged is not recoverable from any table.

Intermediate state survives **only for leads that completed the full pipeline**, persisted as
`signal_json` and `scored_json` on the `leads` row. Every item that died earlier is gone:

| Where an item dies | Code | Currently recorded |
|---|---|---|
| Collector returned nothing | `collectors/*.fetch` | Only an aggregate count in `collector.run` |
| Extraction failed | `extractor.py` → `ExtractionError` | A WARNING log line; a row in `llm_calls` with `outcome='validation_error'` |
| No identifiable company | `extractor.py` → `is_company_identifiable` false | A DEBUG log line only |
| Exact-key duplicate | `dedupe.py` pass 1 | **Nothing** |
| Fuzzy company collision | `dedupe.py` pass 2 | **Nothing** |
| Scoring failed | `scorer.py` returns `None` | A WARNING log line |
| Disqualified | `pipeline.py` filter | **Nothing** — `disqualified_by` is computed then discarded |
| Below threshold | `pipeline.py` filter | **Nothing** |
| Above threshold but past budget | `pipeline.py` `[:daily_research_budget]` | **Nothing** |
| Research returned nothing | `researcher.py` returns `None` | `lead.error` event with company name |
| Draft failed | `drafter.py` returns `None` | A WARNING log line |

Seven of those eleven exits are invisible in the database. Together they account for the large
majority of items in any run.

#### Why this blocks everything else

The diagnostic asymmetry is total. When a **bad** lead reaches Slack, the full chain is on the
`leads` row and the fault is obvious. When a **good** carrier fails to appear, there is nothing to
inspect — and the four plausible causes have four unrelated fixes:

1. The collector never fetched it (C2 — the Indeed collector returns one item per query)
2. The Extractor misread the fields, so the Scorer judged something wrong
3. Dedupe collapsed it into an unrelated company (H2 — "Pacific Freight" vs "Pacific Logistics")
4. Dedupe gave the company's slot to a weaker signal (H3 — dedupe runs before scoring)

**Three of those four are known active bugs.** They are silently dropping leads right now, and
there is no query that can measure how many. Fixing them without stage logging means fixing them
blind, with no before-and-after.

The same gap undermines the eval harness. `run_evals.py` can report that MAE is 22, but not
*why* — whether the Scorer misapplied a rule or the Extractor handed it a wrong `fleet_size` in
the first place. A failing eval you cannot diagnose is a number, not a tool.

#### Proposed fix

One table, one insert per stage transition, including drops.

```sql
CREATE TABLE stage_outputs (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    org_id       TEXT,                -- see MT1
    item_seq     INTEGER NOT NULL,    -- position of the RawItem within the run
    stage        TEXT NOT NULL,       -- collect|extract|dedupe|score|research|draft|deliver
    status       TEXT NOT NULL,       -- passed|dropped|failed
    drop_reason  TEXT,                -- machine-readable, see enum below
    drop_detail  TEXT,                -- human-readable, e.g. the colliding company name
    payload_json TEXT,                -- the object the stage produced, or the input on failure
    source_url   TEXT,                -- carried through so any row links back to the source
    company      TEXT,                -- denormalised for querying without JSON extraction
    created_at   TEXT NOT NULL
);

CREATE INDEX stage_outputs_run     ON stage_outputs(run_id, stage);
CREATE INDEX stage_outputs_company ON stage_outputs(company);
CREATE INDEX stage_outputs_reason  ON stage_outputs(drop_reason);
```

**`drop_reason` values** — keep this a closed set so it can be grouped:
`collector_empty`, `extraction_failed`, `no_company`, `duplicate_exact`, `duplicate_fuzzy`,
`scoring_failed`, `disqualified`, `below_threshold`, `over_budget`, `research_empty`,
`draft_failed`.

**Instrumentation points**, all in `pipeline.py` except where noted:

- After `extract()` — one row per item, `passed` with the `Signal`, or `dropped` with
  `no_company`, or `failed` with `extraction_failed` and the raw title in `drop_detail`
- Inside `dedupe()` — must return the dropped items alongside the survivors, not just the
  survivors. `drop_detail` carries the name it collided with, which is what makes H2 measurable
- After `score()` — always write the `ScoredSignal`, including disqualified and below-threshold
  items. This is the single most valuable row in the table: it is the training set for retuning
  the rules against reply outcomes
- After the budget slice — `over_budget` rows show when the daily cap is the binding constraint
  rather than lead quality
- After `research_company()` and `draft_email()` — `research_empty` and `draft_failed`

**Signature change required:** `dedupe()` currently returns `list[Signal]`. It needs to return
both kept and dropped items with reasons, e.g. `tuple[list[Signal], list[DropRecord]]`.

#### Cost

At 400 raw items per day: roughly 400 extract rows, ~350 dedupe rows, ~300 score rows, ~15 research
and draft rows — about 1,100 inserts per run, a few megabytes per month. Negligible against a
$2.50/day inference bill. Age out with the same retention window used for `dedupe_keys` (MT2).

#### Privacy note

`payload_json` contains scraped third-party content and inferred business information, which makes
this table in-scope for BC PIPA retention and access obligations. Give it an explicit retention
period from the start, scope it by `org_id`, and never expose it across tenants — see the
visibility split in `06-agent-specifications.html`.

#### What it unlocks

```sql
-- Where did this week's items actually die?
SELECT stage, drop_reason, COUNT(*) FROM stage_outputs
WHERE status != 'passed' AND created_at >= datetime('now','-7 days')
GROUP BY stage, drop_reason ORDER BY 3 DESC;

-- Which companies is fuzzy dedupe eating? (measures H2)
SELECT company, drop_detail, COUNT(*) FROM stage_outputs
WHERE drop_reason = 'duplicate_fuzzy' GROUP BY company, drop_detail;

-- Is the budget or the threshold the binding constraint?
SELECT drop_reason, COUNT(*) FROM stage_outputs
WHERE drop_reason IN ('below_threshold','over_budget') GROUP BY drop_reason;

-- Trace one company end to end, including the stage that killed it
SELECT stage, status, drop_reason, created_at FROM stage_outputs
WHERE company LIKE 'Northbound%' ORDER BY created_at;
```

The last query is the one that matters day to day: it turns "why didn't this carrier show up" from
speculation into a lookup.

---

## MULTI-TENANCY

These are latent today — the system runs single-tenant, so nothing is currently broken in
production. Every one of them becomes live the moment a second organisation is added, and three
are schema changes that are far cheaper now than after there is data to migrate.

### MT1. `leads` has no `org_id` — dedupe is global across tenants

**Severity: CRITICAL once multi-tenant.**

`runs` and `llm_calls` both carry `org_id`. `leads` does not — in either backend (`store.py`
schema, and the Supabase `leads` upsert in `store_supabase.py`). Neither does `dedupe_keys`.

Combined with `recent_company_names(days=30)`, which filters on date only:

```python
# store.py
rows = con.execute(
    "SELECT signal_json FROM leads WHERE created_at >= datetime('now', ?)",
    (f"-{days} days",),
)   # no org filter, no vertical filter
```

**Effect:** customer A's run sees Northbound Logistics. Customer B's run that afternoon finds the
same carrier and silently drops it — even though B has never contacted them and it may be B's best
lead of the week. Two customers in the same vertical quietly cannibalise each other's pipelines,
with no log line on either side.

This is also a confidentiality problem, not only a correctness one: B's pipeline behaviour becomes
dependent on A's activity, which is a side channel.

**Fix:** add `org_id` to `leads` and `dedupe_keys`, filter every dedupe read by it, and add it to
the `dedupe_key` UNIQUE constraint as a composite. Do this before the second customer, not after.

### MT2. `seen_dedupe_keys()` is unscoped and unbounded

Both backends load every key ever written, with no org filter and no date filter, on every run.
Compounds MT1 and gets slower forever. Query by key with an org filter instead of loading the set.

### MT3. `_DB_PATH` is a mutable module global

`store.py`
```python
_DB_PATH = os.environ.get("ROXI_DB_PATH", "roxi.db")

def init_db(path: str | None = None) -> None:
    global _DB_PATH
    if path:
        _DB_PATH = path
```

`pipeline.run()` calls `init_db()` at the top of every run. Once more than one run executes
concurrently in the same process, they share this global. Any code path passing an explicit path
redirects every other in-flight run's writes.

**Fix:** pass the path (or a connection factory) explicitly, or make it a contextvar. This matters
as soon as runs are executed by a worker pool.

### MT4. `USE_SUPABASE` does nothing

`store_supabase.py` docstring:

> Activate by setting `USE_SUPABASE=1` in the environment. `store.py` auto-delegates to this
> module when that env var is present.

`store.py` contains no such delegation. There is no import of `store_supabase`, no env check, no
dispatch. Setting the variable has zero effect and everything continues writing to SQLite.

**Effect:** someone follows the documented setup, sees no error, and believes they have migrated.
The Supabase tables stay empty and the local `roxi.db` keeps growing.

**Severity: HIGH** — silent, and the failure mode is believing a migration succeeded.

### MT5. `store_supabase.py` is a partial interface

The docstring claims "the interface is identical: same function names and signatures." It is not.
Present: `init_db`, `save`, `update_status`, `pending_leads`, `recent_company_names`,
`seen_dedupe_keys`, `log_llm_call`, `log_publish`.

Missing, but called by `pipeline.py`, `dispatcher.py`, `responder.py`, and the API layer:
`start_run`, `finish_run`, `get_run_cost`, `get_lead`, `find_lead_by_short_id`, `list_leads`,
`get_stats`, `list_runs`, `get_run`, `list_llm_calls`, `list_events`, `daily_costs`,
`is_suppressed`, `add_to_suppression_list`, `list_suppression`,
`remove_from_suppression_list`, `record_generation_cost`.

If MT4 were fixed as written, the first run would `AttributeError` on `store.start_run`. Note that
`is_suppressed` is on that list — a partially wired Supabase backend could send without a
suppression check.

**Fix:** complete the module, then have `store.py` delegate through a single accessor. Add a test
that asserts both modules expose the same public names.

### MT6. Naive and aware timestamps mixed between backends

`store.py` writes `datetime.now(timezone.utc).isoformat()` (aware). `store_supabase.py` writes
`datetime.utcnow().isoformat()` (naive, and deprecated in Python 3.12+). Rows written by the two
backends sort and compare inconsistently, which corrupts the 30-day dedupe window and every cost
report spanning a migration.

**Fix:** one helper, used by both.

### MT7. Deployment note — no per-customer compute required

Recorded here because the question recurs. A run is stateless and already scoped by `org_id` and
vertical, so any worker can execute any customer's run. The right topology is a scheduler
enqueueing one job per (org, vertical) per day and a pool of identical workers — which is what
`Procfile` and `railway.json` already describe.

Isolation belongs at the row and config level: `org_id` on every table (MT1), per-org spend caps,
per-org rate limits, scoped credentials.

The one genuine argument for compute separation is **scraping egress**. If one customer's job-board
queries get the shared IP blocked, every customer's collector breaks together. That argues for
per-org proxies or egress IPs in the collector layer — not per-org application containers. A
contractually mandated dedicated deployment is the other case; charge for it rather than designing
around it.

---

## Suggested fix order

1. **C1** — nothing downstream can be tested while Sonnet calls fail
2. **M7** — stage logging, *before* fixing the silent-loss bugs, so their effect is measurable
3. **L1** — run the eval harness to establish a baseline *before* changing prompts or scoring
4. **C2** — the Phase 1 collector is the input to everything
5. **H2, H3** — dedupe correctness, both silent-loss bugs
6. **H4, M1, M2, M3** — cost accuracy and trace completeness
7. **MT1, MT2, MT3** — schema changes; cheap now, expensive once there is data to migrate
8. **H1, M5** — must be fixed before any real send; they are the CASL-facing defects
9. **MT4, MT5, MT6** — before any Supabase migration is attempted
10. **M4, M6, L2, L3** — hygiene

Items 1–5 are prerequisites for a trustworthy Phase 1 run. Item 8 is a prerequisite for Phase 3.
Items 7 and 9 are prerequisites for Phase 6 — but item 7 is worth doing early regardless, since
adding a column is trivial today and a migration later.

**On the ordering of M7:** it is placed second deliberately. H2 and H3 are silently dropping leads
today, and without stage logging there is no way to measure how many before the fix or confirm the
fix worked after. Add `stage_outputs` and `org_id` (MT1) in the same migration, since both touch
the schema.
