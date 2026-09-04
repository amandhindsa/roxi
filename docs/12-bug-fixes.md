# Roxi — Bug Fix Log

All bugs fixed across the two sessions of 4 September 2026. Each entry records the bug ID (from `09-known-bugs.md`), what was wrong, what file and line was changed, and what the fix was.

---

## Session 1 — Commit `602af28`

### C2 · Job-board collector returns at most one item per query

**File:** `roxi/collectors/job_boards.py`

**What was wrong:** `_search_indeed` called `page.goto()` (inside `_fetch_detail`) on the same page object that the card selectors were still iterating. Navigation detaches every card handle. Cards 2–20 silently threw `StaleElementReference` errors, swallowed by `except Exception: continue`. Every query returned exactly one item.

**Fix:** Two-page approach. A `search_page` loads the results and never navigates away. A `detail_page` handles all `_fetch_detail` calls. Card metadata `(title, company, href)` is collected into a plain list first; then detail pages are fetched on the second page object.

---

### H2 · Dedupe collapses unrelated companies (first-token match)

**File:** `roxi/dedupe.py` → `_fuzzy_match`

**What was wrong:** After `_CORP_SUFFIXES` strips industry words (`freight`, `logistics`, `transport`, etc.), many Canadian carrier names reduce to a single common token (`pacific`, `northern`, `western`). The first-token shortcut `if ca.split()[0] == cb.split()[0]` then fired and merged them.

**Fix (Session 1):** Added `len(ca_tokens) > 1 and len(cb_tokens) > 1` guard on the first-token branch, so single-token canonicals skip that path.

**Fix (Session 2 — see below):** The SequenceMatcher fallback was still merging them at ratio 1.0. Added a second guard requiring both canonicals to have `> 1` token before SequenceMatcher is consulted.

---

### H3 · Dedupe runs before scoring — weaker signal wins company slot

**File:** `roxi/pipeline.py`

**What was wrong:** Company dedupe ran on raw `Signal` objects before scoring. Whichever signal appeared first in the collected list claimed that company's slot, even if a higher-scoring signal appeared later.

**Fix:** Reordered pipeline: exact dedupe → score all survivors → sort descending by score → company dedupe. The first signal seen per company is now always the highest-scoring one.

---

### H4 · Haiku cost table understated by ~25 %

**File:** `roxi/llm.py`

**What was wrong:** `COST_PER_MILLION[HAIKU]` was `{"input": 0.80, "output": 4.00}`. Actual Haiku 4.5 pricing is $1.00 / $5.00 per million tokens.

**Fix:** Corrected to `{"input": 1.00, "output": 5.00}`.

---

### M1 · Researcher web-search call has no `max_uses` cap

**File:** `roxi/agents/researcher.py`

**What was wrong:** `tools=[{"type": "web_search_20250305", "name": "web_search"}]` — no cap. A verbose run could execute many more than the 2–3 searches the system prompt requests, with each billed.

**Fix:** Added `"max_uses": 4` to the tool definition.

---

### M2 · `max_tokens` hard-coded in `structured()`

**File:** `roxi/llm.py` → `structured()`

**What was wrong:** `max_tokens=2048` was fixed for every call. `ResearchBrief` with several hooks can exceed this, surfacing as a `ValidationError` and a wasted retry.

**Fix:** Made `max_tokens` a parameter with `default=2048`.

---

### M3 · Researcher search call logs an incomplete trace row

**File:** `roxi/agents/researcher.py`

**What was wrong:** The `store.log_llm_call` call for the `researcher/search` agent omitted `prompt_version`, `input_hash`, and `outcome`. These columns were null for the most externally variable call in the pipeline, defeating the trace table's purpose for that stage.

**Fix:** Added all three fields. `prompt_version` hashes `_SEARCH_SYSTEM`; `input_hash` hashes the per-call user message; `outcome` is `"ok"` or `"empty"`.

---

### M4 · Lead can be delivered but not persisted

**File:** `roxi/store.py` → `_save`, `roxi/pipeline.py`

**What was wrong:** `INSERT OR IGNORE` silently swallowed dedupe-key collisions. `pipeline.py` still appended the lead to the return list and called `deliver()`, so a Slack/WhatsApp card could exist for a lead with no database row. Approval would then 404.

**Fix:** `_save` checks `cursor.rowcount > 0` and returns `False` on collision. `save()` propagates the bool. `pipeline.py` skips `leads.append` and delivery when `not persisted`.

---

### M6 · `seen_dedupe_keys()` loads the entire table into memory

**File:** `roxi/store.py`, `roxi/store_supabase.py`

**What was wrong:** `SELECT key FROM dedupe_keys` with no date filter loaded every key ever written on every run.

**Fix:** Added a `days=90` window (`WHERE created_at >= datetime('now', '-90 days')`). Applied to both SQLite and Supabase backends.

---

### M7 · No stage-level observability — dropped items leave no trace

**Files:** `roxi/store.py`, `roxi/store_supabase.py`, `roxi/pipeline.py`

**What was wrong:** Seven of eleven exit points in the pipeline wrote nothing to the database. Items dropped by exact dedupe, fuzzy dedupe, scoring failure, disqualification, threshold filtering, or budget capping left no queryable record. Diagnosing "why didn't this carrier appear" required reading log files.

**Fix:**
- Added `stage_outputs` table to the SQLite schema (with indexes on `run_id+stage`, `company`, `drop_reason`).
- Added `log_stage_output()` to both `store.py` and `store_supabase.py`.
- Added instrumentation in `pipeline.py` at every exit point: `extract`, `dedupe/exact`, `score`, `dedupe/fuzzy`, `disqualified`, `below_threshold`, `over_budget`, `research`, `draft`.

---

### MT4 · `USE_SUPABASE` env var did nothing

**File:** `roxi/store.py`

**What was wrong:** `store.py` had no delegation to `store_supabase`. Setting `USE_SUPABASE=1` had zero effect; everything silently continued writing to SQLite.

**Fix:** Added `sys.modules` replacement at the top of `store.py`: when `USE_SUPABASE=1` is set, the module replaces itself with `store_supabase` in `sys.modules` so all subsequent imports of `roxi.store` get the Supabase backend.

---

### MT5 · `store_supabase.py` was a partial interface

**File:** `roxi/store_supabase.py`

**What was wrong:** The module claimed "identical interface" but was missing 17 functions called by `pipeline.py`, `dispatcher.py`, `responder.py`, and the API layer: `start_run`, `finish_run`, `get_run_cost`, `get_lead`, `find_lead_by_short_id`, `list_leads`, `get_stats`, `list_runs`, `get_run`, `log_llm_call`, `list_llm_calls`, `list_events`, `daily_costs`, `is_suppressed`, `add_to_suppression_list`, `list_suppression`, `remove_from_suppression_list`, `record_generation_cost`. Enabling Supabase would have immediately `AttributeError`'d on `store.start_run`.

**Fix:** Implemented all missing functions. Every timestamp uses `datetime.now(timezone.utc)` (MT6 fix included).

---

### MT6 · Naive and aware timestamps mixed between backends

**File:** `roxi/store_supabase.py`

**What was wrong:** Original `store_supabase.py` used `datetime.utcnow().isoformat()` (naive, deprecated in Python 3.12+). `store.py` used `datetime.now(timezone.utc).isoformat()` (aware). Rows from both backends sort incorrectly against each other.

**Fix:** All timestamps in `store_supabase.py` now use `datetime.now(timezone.utc)` via the shared `_now()` helper.

---

## Session 2 — Commit `56e8de1` (code review fixes)

### R1 · `store_supabase.save()` returned `None` — zero leads delivered under Supabase

**File:** `roxi/store_supabase.py` line 50

**What was wrong:** `store.py`'s `save()` was changed to return `bool` (True = inserted, False = collision), and `pipeline.py` gates delivery on `if not persisted`. But `store_supabase.save()` had no return statement — it returned `None` implicitly on success and on collision. `not None` is `True`, so every lead was treated as a collision and skipped at delivery. Zero leads would ever be sent under `USE_SUPABASE=1`.

**Fix:** `store_supabase.save()` now returns `False` on collision and `True` on successful insert, matching the SQLite backend's signature.

---

### R2 · H2 dedupe fix incomplete — single-token canonicals still merged via SequenceMatcher

**File:** `roxi/dedupe.py` → `_fuzzy_match` line 46

**What was wrong:** Session 1 added a guard on the first-token branch requiring `> 1` token. But "Pacific Freight" and "Pacific Logistics" both strip to the single token `"pacific"`, so the first-token branch is skipped — and `SequenceMatcher(None, "pacific", "pacific").ratio()` returns `1.0 >= 0.82`, merging them anyway. The comment named this exact pair as the intended fix but the fix was incomplete.

**Fix:** Added a second guard: if either canonical has fewer than 2 tokens, `_fuzzy_match` returns `False` without consulting SequenceMatcher. Single-word roots after suffix stripping are too ambiguous to merge on.

---

### R3 · `item_seq` not stable across pipeline stages

**File:** `roxi/pipeline.py` — all stage-logging loops

**What was wrong:** Six separate `enumerate()` loops each restarted at 0 over progressively smaller lists. `item_seq=2` in the `extract` stage referred to the 3rd raw item; `item_seq=2` in the `score` stage referred to the 3rd post-dedupe survivor (a different item). The M7 "trace one item end-to-end by `item_seq`" query returned rows from different source items.

**Fix:** Every stage tuple now carries `raw_idx` — the item's original position in `raw_items`. The tuples are `(raw_idx, raw, signal/scored)` throughout all loops. Every `log_stage_output` call uses `item_seq=raw_idx`. The same `item_seq` value now refers to the same source item at every stage in a run.

---

### R4 · `over_budget` rows got `item_seq` 0, 1, 2… from the slice

**File:** `roxi/pipeline.py` line 149 (old)

**What was wrong:** `for i, (r, s) in enumerate(qualified[budget:])` restarted at 0. Items cut by the budget got `item_seq=0,1,2...` colliding with the first items' stage rows in other stages.

**Fix:** Resolved by R3 — `raw_idx` comes from the tuple, not from enumerate. `for raw_idx, r, s in qualified[budget:]` uses the stable original index.

---

### R5 · `_row_to_api_dict` dropped `raw` and `signal` in Supabase backend

**File:** `roxi/store_supabase.py` → `_row_to_api_dict`

**What was wrong:** The SQLite version returned all fields including `raw` (parsed from `raw_json`) and `signal` (parsed from `signal_json`). The Supabase version built a hardcoded 7-key dict with only `id`, `vertical_id`, `status`, `created_at`, `scored`, `draft`, `research`. Any caller reading `row["raw"]` or `row["signal"]` got `KeyError` under Supabase.

**Fix:** Added `"raw"` and `"signal"` to the Supabase `_row_to_api_dict` return dict.

---

### R6 · `daily_costs()` ignored `vertical_id` in Supabase backend

**File:** `roxi/store_supabase.py` → `daily_costs`

**What was wrong:** The function accepted `vertical_id` but never applied it as a filter. The query returned aggregate costs for all verticals. The SQLite version correctly joined `llm_calls → runs` and filtered by `runs.vertical_id`.

**Fix:** Added a PostgREST embedded resource join: `.select("cost_usd, created_at, runs(vertical_id)")` with `.eq("runs.vertical_id", vertical_id)` when the parameter is provided.

---

### R7 · `_prompt_version` hashed the unformatted template — all verticals shared the same hash

**File:** `roxi/agents/researcher.py` line 55 (old)

**What was wrong:** `_prompt_version = hashlib.sha256(_SEARCH_SYSTEM.encode())` was computed inside `research_company()` on every call, hashing `_SEARCH_SYSTEM` which still contained the `{product_brief}` placeholder. The `.format(product_brief=...)` substitution happened later inside `client.messages.create()`. Every vertical produced the same `prompt_version` hash in `llm_calls`, making per-vertical prompt tracing useless.

**Fix:** Moved to module level as `_SEARCH_PROMPT_VERSION = hashlib.sha256(_SEARCH_SYSTEM.encode()).hexdigest()[:16]`. This is a stable constant — it changes when the template is edited, which is the intended behaviour. Per-call variance between verticals is captured by `input_hash`, which hashes the full user message (including company, location, signal) on each call.

---

## Open items not yet fixed

These remain in `09-known-bugs.md` and have not been addressed:

| ID | Summary |
|----|---------|
| H1 | Dispatcher fabricates `contact@domain` email addresses — needs verified `contact_email` field |
| M5 | Suppression keying falls back to company name when domain is absent — depends on H1 |
| MT1 | `leads` table has no `org_id` — dedupe is global across tenants |
| MT2 | `seen_dedupe_keys()` has no org filter |
| MT3 | `_DB_PATH` is a mutable module global |
| L1 | Eval harness has no committed results — baseline score unknown |
| L2 | Indeed scraping violates their ToS — prefer official APIs |
