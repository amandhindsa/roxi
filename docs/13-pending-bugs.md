# Roxi — pending bugs

What is still broken after the fixes recorded in `12-bug-fixes.md`. Verified against the code on
4 September 2026, not taken from the fix log.

The original catalogue is `09-known-bugs.md`. This document supersedes its status column: anything
listed here is still open.

---

## BLOCKING — nothing works properly until this is fixed

### P1. Model names are still wrong, and now falsely marked as verified

**Was: C1. The fix log does not mention it. The open-items table does not mention it. It has fallen
out of tracking entirely.**

`roxi/llm.py`, current contents:

```python
# Model name constants — verified 2026-09-04 against console.anthropic.com/docs/models
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"      # not a current model
OPUS = "claude-opus-4-8"          # not a current model
```

Correct values are `claude-sonnet-5` and `claude-opus-5`.

**Why this is worse than it was before.** Somebody edited this exact block — the Haiku pricing
directly beneath it was corrected as part of the H4 fix — and added a comment claiming the model
names were verified against Anthropic's documentation. They were not. The comment now asserts
confidence that was never earned, which makes the bug harder to find than if there were no comment
at all.

**Effect.** Extraction and scoring work, because they use Haiku. Research and drafting fail on
every lead, because they use Sonnet. A run collects, extracts and scores, then delivers zero leads
and looks like a quiet day.

**Where to change it:** `roxi/llm.py`, `roxi/config.py` (`ModelsConfig` defaults),
`verticals/hauler_ai.yaml`, `verticals/hvac_trades.yaml`, and `roxi/agents/compiler.py`
(`_EmittedConfig` defaults — otherwise every new vertical the interview creates is born broken).

**Then remove the duplication.** The reason this bug is in five files is that the names are typed
by hand in each. Have the config and YAML read from the constants in `llm.py`. Delete the
verification comment unless someone has actually checked the docs that day.

---

## HIGH

### P2. The Supabase switch depends on import order

**New — introduced by the MT4 fix.**

`roxi/store.py` replaces itself in `sys.modules` when `USE_SUPABASE=1`:

```python
if os.environ.get("USE_SUPABASE") == "1":
    import sys
    from roxi.store_supabase import *
    sys.modules[__name__] = sys.modules["roxi.store_supabase"]
```

The comment above it states that "every call site imports roxi.store fresh and gets the replaced
module." That is not true of every call site.

`roxi/llm.py` line 11 does `from roxi.store import log_llm_call` at module load. Any module that
imports `llm` before the swap has completed captures the SQLite function object directly, and keeps
writing model-call traces to SQLite forever while everything else writes to Supabase.

Whether this happens depends on import order, which nothing enforces. It fails silently and
produces a split-brain trace table.

**Fix:** replace the module-swap with an explicit accessor.

```python
def _backend():
    if os.environ.get("USE_SUPABASE") == "1":
        from roxi import store_supabase
        return store_supabase
    return _sqlite
```

Call sites use `store.log_llm_call(...)` rather than importing the function by name. Also change
`llm.py` to `from roxi import store` and call `store.log_llm_call(...)`.

### P3. Dispatcher still fabricates recipient email addresses

**Was: H1. Unchanged.**

`roxi/dispatcher.py` builds the recipient as `contact@{company_domain}`. The guard above it checks
that a *domain* exists, not that a verified *address* does — while its own comment says it "cannot
send email to a fabricated address."

Most guessed addresses bounce, which damages the sending domain's reputation. Under CASL, sending
to an invented address also weakens any implied-consent position, since implied consent attaches to
a conspicuously published address.

**Fix:** add a verified `contact_email` to the lead, populated by enrichment or by the reviewer at
approval time. No address, no send.

**This blocks Phase 3.** Do not send anything from the Dispatcher until it is fixed.

### P4. Suppression is keyed inconsistently

**Was: M5. Unchanged, and depends on P3.**

`dispatcher.py` and `responder.py` both key suppression on `company_domain or company`. The same
business is suppressed under its domain on one run and its name on another, depending on whether
enrichment found a domain. A suppression added under one key will not match the other.

An unsubscribe request can therefore silently fail to take effect. Of everything in this document,
this is the item with actual legal consequence.

**Fix:** key on a single canonical identifier — the verified contact email from P3 — with no
fallback.

---

## MULTI-TENANT — latent today, live at customer two

### P5. `leads` and `dedupe_keys` have no `org_id`

**Was: MT1. Unchanged.**

`runs` and `llm_calls` carry `org_id`. `leads` and `dedupe_keys` do not, and
`recent_company_names()` filters on date only.

Two customers in the same industry will silently suppress each other's leads, with no log line on
either side. It is also a confidentiality problem: one customer's pipeline behaviour becomes
dependent on another's activity.

**Fix:** add `org_id` to both tables, filter every dedupe read by it, and make the `dedupe_key`
uniqueness constraint composite. Do this before the second customer, not after — it is a column
addition today and a data migration later.

### P6. `seen_dedupe_keys()` has no org filter

**Was: MT2. Partially fixed.** The 90-day window was added, which fixes the unbounded growth. The
missing org filter remains, and it is the half that matters. Resolve alongside P5.

### P7. `_DB_PATH` is a mutable module global

**Was: MT3. Unchanged.**

```python
_DB_PATH = os.environ.get("ROXI_DB_PATH", "roxi.db")

def init_db(path: str | None = None) -> None:
    global _DB_PATH
    if path:
        _DB_PATH = path
```

`pipeline.run()` calls `init_db()` at the start of every run. Once two runs execute concurrently in
one process, they share this global, and any call passing an explicit path redirects every other
in-flight run's writes.

Harmless today because runs are sequential. Becomes real the moment a worker pool exists.

---

## MEDIUM

### P8. The registry collector does not do what it exists to do

**Not previously logged.**

`roxi/collectors/registry.py` exists to find carriers who *recently* received operating authority.
The timing is the entire signal.

- `_fmcsa_search_province` accepts a `cutoff` date and never uses it. Nothing is filtered by date.
- The FMCSA search selects `query_type=MC_NUMBER` without supplying a number, so it is unlikely to
  return the intended "recently granted authority" result set at all.
- `_nsc_search` submits an empty carrier name and takes the first fifty active carriers, with no
  date filter.

Even working perfectly, this returns *a list of carriers*, not *a list of newly registered
carriers*. The feature is not implemented, rather than broken.

The channel is disabled in both vertical configs, so nothing is currently affected. It should stay
disabled until the date filtering exists, otherwise it will flood the pipeline with untargeted
companies.

### P9. Reddit search terms are hardcoded to trucking

**Not previously logged.**

`roxi/collectors/reddit.py` contains a module-level list:

```python
_SEARCH_TERMS = ["eManifest", "CBSA customs", "cross-border trucking software",
                 "TMS dispatch Canada US", "customs paperwork carrier",
                 "FMCSA authority Canada"]
```

Subreddits come from the vertical config; what is searched for does not. Enabling Reddit for the
HVAC vertical would search plumbing and electrical forums for customs paperwork.

**Fix:** move the terms into the vertical config alongside the subreddit list.

### P10. Domain vocabulary is still hardcoded in three prompts and the shared data model

**Not previously logged as a bug. Detail in the generalisation discussion.**

- `models.py` — `Signal.fleet_size`, `poster_role` including the value `"driver"`, `signal_type`
  fixed to `hiring | authority_grant | pain_complaint`, and `ResearchBrief.fleet_estimate` /
  `operating_lanes`
- `agents/researcher.py` — the prompt asks for fleet size, number of trucks, cross-border lanes,
  and TMS
- `agents/drafter.py` — the prompt states recipients are "operations managers and owners at
  trucking companies"
- `dedupe.py` — the stripped name suffixes are transport words

The Drafter one is the serious one, because it reaches the customer: HVAC emails are currently
written as though addressed to a trucking company. The rest degrade quality quietly.

`verticals/hvac_trades.yaml` already exists, so this is live, not hypothetical.

**Fix:** move the domain language into the vertical config — an audience description for the
Drafter, research targets for the Researcher, role vocabulary for the Extractor, name suffixes for
dedupe — and neutralise the schema fields.

---

## PROCESS

### P11. The eval harness has still never been run

**Was: L1. Unchanged. `evals/results/` is empty and `tests/` is empty.**

Thirteen defects were fixed in session one and seven more in session two, several of them touching
scoring and dedupe behaviour directly. There is no before-and-after measurement for any of them.

**This is the most important open item after P1.** The harness exists at `evals/run_evals.py` with
fifty labelled fixtures. Running it costs pennies and a few minutes.

**Worth noting about the fix sessions.** Seven new bugs (R1–R7) were introduced while fixing
thirteen, and one blocking bug was skipped while being marked as verified. That is a normal ratio
for unmeasured refactoring, and it is the argument for establishing a baseline before continuing.
Fix P1, run the evals, record the result, and only then keep going.

### P12. Indeed scraping violates their terms

**Was: L2. Unchanged.** The job-board collector is the most legally exposed component and the most
fragile. The Government of Canada Job Bank publishes structured data intended for reuse and would
remove both problems.

---

## Order

1. **P1** — five files. Nothing produces output until this is done.
2. **P11** — run the evals immediately after P1 and commit the result. This is the baseline.
3. **P2** — before anyone tries Supabase again.
4. **P5, P6, P7** — schema changes, cheap now.
5. **P3, P4** — before any real send. These gate Phase 3.
6. **P9, P10** — before a second industry goes live.
7. **P8, P12** — when the relevant channel is next touched.

---

## Fixed — 4 September 2026

### P1 — Model names
Already fixed in the previous session (see `12-fix-these-two-first.md`). Not repeated here.

### P2 — Supabase import order
Replaced the `sys.modules` swap in `store.py` with a `_backend()` function that checks
`USE_SUPABASE` at call time and returns `store_supabase` or `None`. Every public function in
`store.py` now delegates to `_backend()` before running its SQLite implementation.

`roxi/llm.py` changed from `from roxi.store import log_llm_call` (captured at import time) to
`from roxi import store as _store` and `_store.log_llm_call(...)` (resolved at call time).

`roxi/outcome.py` changed from `from roxi.store import update_status` to `from roxi import store`
and `store.update_status(...)` for the same reason.

### P3 — Fabricated email addresses
Added `contact_email: Optional[str] = None` to `Lead` in `models.py` (field already existed from a
prior session; confirmed present).

`dispatcher.py`: blocks any send where `lead.contact_email` is `None`, uses `lead.contact_email`
as the email address sent to Instantly (replaces `contact@{company_domain}`), and uses
`lead.contact_email` as the suppression key.

`store.py` and `store_supabase.py`: `_save()` and `save()` persist `contact_email`; `_row_to_lead()`
reads it back. `update_contact_email(lead_id, email)` added to both stores.

### P4 — Suppression keyed inconsistently
`dispatcher.py`: suppression is now keyed on `lead.contact_email` — the same identifier used for
the send — instead of `company_domain or company`.

`responder.py`: suppression key is `lead.contact_email` when present, falling back to
`company_domain or company` (a reply can only arrive after a send, so `contact_email` will almost
always be set).

### P5 — leads and dedupe_keys have no org_id
`store.py` schema: `leads` and `dedupe_keys` tables now include `org_id TEXT` and `subscription_id TEXT`
columns (CREATE TABLE IF NOT EXISTS — existing databases need a manual ALTER TABLE or recreate).

`save()` signature updated to `save(lead, vertical_id, org_id=None, subscription_id=None)`.
`store_supabase.save()` updated to match.

`pipeline.py`: `store.save(...)` now passes both `org_id` and `subscription_id`.

### P6 — seen_dedupe_keys() has no org filter
`store.py` and `store_supabase.py`: `seen_dedupe_keys(subscription_id=None, days=90, org_id=None)`
filters by `subscription_id` when provided (matching what `pipeline.py` already passes), with
`org_id` as a legacy fallback.

### P7 — _DB_PATH is a mutable module global
`store.py`: removed `_DB_PATH` module variable and the `global _DB_PATH` mutation in `init_db`.
Replaced with a `_db_path()` function that reads `ROXI_DB_PATH` from the environment fresh at
each call. `_conn()` now calls `_db_path()` each time it opens a connection.

### P9 — Reddit search terms hardcoded to trucking
`config.py`: added `search_terms: list[str] = []` to `ChannelReddit`.
`collectors/reddit.py`: replaced the module-level `_SEARCH_TERMS` list with
`vertical.channels.reddit.search_terms`.
`verticals/hauler_ai.yaml` and `verticals/hvac_trades.yaml`: each has its own domain-appropriate
`search_terms:` list under the `reddit:` section.

### Still open
P8 (registry collector), P10 (domain vocabulary), P11 (eval harness), P12 (Indeed ToS).
