# Roxi — technical build plan

Companion to `05-roxi-implementation-plan.md`. That doc defines *what* to build and *when* to stop.
This doc defines *how* to build it: repo layout, module boundaries, interfaces, and the engineering
sequence. Read both together.

Compiled 3 September 2026.

---

## 1. Repository layout

```
roxi/
├── verticals/
│   └── hauler_ai.yaml          # the only vertical until Phase 6
├── roxi/
│   ├── __init__.py
│   ├── config.py               # loads and validates a vertical YAML
│   ├── models.py               # Pydantic types: RawItem → Signal → ScoredSignal → …
│   ├── llm.py                  # single structured() call wrapper (cost + trace)
│   ├── pipeline.py             # sequential orchestration — no agent loops
│   ├── agents/
│   │   ├── compiler.py         # Phase 5 — emits VerticalConfig from a plain-English brief
│   │   ├── extractor.py
│   │   ├── scorer.py
│   │   ├── researcher.py
│   │   └── drafter.py
│   ├── collectors/
│   │   ├── base.py             # Collector protocol / ABC
│   │   ├── job_boards.py       # Phase 1
│   │   ├── registry.py         # Phase 2
│   │   └── reddit.py           # Phase 3
│   ├── dedupe.py               # exact key + fuzzy company match, pure Python
│   ├── store.py                # SQLite now; Supabase swap is one file change
│   ├── delivery.py             # Slack webhook, formats the approval card
│   └── outcome.py              # records sent / replied against a lead ID
├── evals/
│   ├── fixtures/
│   │   └── hauler_ai.jsonl     # 50 hand-labelled RawItems + expected scores
│   ├── run_evals.py            # scores all fixtures, reports MAE + recall
│   └── results/                # one JSON file per run, committed
├── tests/
│   ├── test_models.py
│   ├── test_dedupe.py
│   ├── test_extractor.py
│   └── test_scorer.py
├── scripts/
│   └── backfill.py             # one-off data operations, not part of pipeline
├── pyproject.toml
├── .env.example
└── README.md
```

**Rules:**
- No vertical-specific logic anywhere under `roxi/`. Vertical behaviour lives in YAML only.
- `pipeline.py` is the only file allowed to import from `agents/`. Everything else is called through the pipeline.
- `llm.py` is the only file allowed to call the Anthropic SDK.

---

## 2. Data model (Python)

Defined in `roxi/models.py` using Pydantic v2. These are the typed handoffs between agents.

```python
class RawItem(BaseModel):
    channel: str          # "job_boards" | "registry" | "reddit"
    source_url: str
    fetched_at: datetime
    title: str
    body: str

class Signal(BaseModel):
    company: str
    company_domain: str | None
    location: str | None
    fleet_size: int | None
    signal_type: str      # "hiring" | "authority_grant" | "pain_complaint"
    signal_date: date | None
    evidence: str         # verbatim sentence from source — required
    poster_role: str      # "decision_maker" | "driver" | "unknown"
    is_company_identifiable: bool

class ScoredSignal(Signal):
    score: int            # 0–100
    rules_fired: list[dict]   # [{"rule": str, "delta": int}]
    reasoning: str        # internal; never shown to the reviewer
    disqualified_by: str | None

class ResearchBrief(BaseModel):
    company_summary: str
    fleet_estimate: str | None
    operating_lanes: list[str]
    current_stack_guess: str | None
    decision_maker_title: str | None
    hooks: list[str]
    confidence: str       # "high" | "medium" | "low"

class EmailDraft(BaseModel):
    why_now: str
    subject: str
    body: str
    hook_used: str

class Lead(BaseModel):
    id: str               # UUID
    raw: RawItem
    signal: Signal
    scored: ScoredSignal
    research: ResearchBrief | None
    draft: EmailDraft | None
    dedupe_key: str
    status: str           # "pending" | "approved" | "rejected" | "sent" | "replied"
    created_at: datetime
```

`evidence` on `Signal` is validated non-empty — the model layer enforces what the architecture doc specifies.

---

## 3. The `structured()` wrapper

All model calls go through one function in `roxi/llm.py`:

```python
def structured(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[BaseModel],
    max_retries: int = 1,
) -> BaseModel:
```

Internally: builds the tool definition from `schema.model_json_schema()`, calls with
`tool_choice={"type": "tool", "name": schema.__name__}`, validates the result, retries once on
validation failure with the error fed back as a tool result, raises `ExtractionError` on second
failure. Logs model, input tokens, output tokens, cost estimate, and latency to a `llm_calls`
SQLite table on every call.

No agent touches the Anthropic client directly.

---

## 4. Vertical YAML schema

`verticals/hauler_ai.yaml` — the complete configuration for one vertical:

```yaml
vertical_id: hauler_ai
product_brief: |
  Hauler AI automates cross-border customs paperwork for Canadian carriers. It replaces
  manual eManifest entry and integrates with existing TMS workflows.

icp:
  description: Canadian trucking carriers, 10–100 power units, cross-border freight
  disqualifiers:
    - fewer than 8 trucks
    - owner-operator (single driver)
    - asset-free broker
    - US-domiciled with no Canadian operations
    - already on a modern TMS (McLeod, TMW, Samsara)

scoring_rules:
  - rule: New or expanded US operating authority
    delta: +35
  - rule: Hiring dispatcher, safety officer, or fleet manager
    delta: +25
  - rule: Public complaint about eManifest or legacy TMS
    delta: +30
  - rule: Fleet size 10–100 power units (confirmed)
    delta: +10
  - rule: Poster is decision-maker (owner, ops manager)
    delta: +10
  - rule: Fleet size under 8 (confirmed)
    delta: disqualify
  - rule: Already on modern TMS
    delta: disqualify

qualify_threshold: 60

channels:
  job_boards:
    enabled: true
    queries:
      - "dispatcher carrier BC"
      - "safety officer trucking AB"
      - "fleet manager transport ON SK MB"
  registry:
    enabled: false   # Phase 2
  reddit:
    enabled: false   # Phase 3
    subreddits: [r/Truckers, r/canadalandlords]  # placeholder

models:
  extractor: claude-haiku-4-5-20251001
  scorer: claude-haiku-4-5-20251001
  researcher: claude-sonnet-5
  drafter: claude-sonnet-5

daily_research_budget: 20   # max Researcher calls per day
```

`config.py` loads this, validates it against a Pydantic `VerticalConfig` model, and makes it
available to the pipeline. The pipeline never reads the YAML directly.

---

## 5. Pipeline (sequential, readable)

`roxi/pipeline.py` — the full run for one vertical:

```python
def run(vertical: VerticalConfig) -> list[Lead]:
    raw_items = collect_all(vertical)           # all enabled collectors
    signals = [extract(r, vertical) for r in raw_items]
    signals = [s for s in signals if s is not None]
    signals = dedupe(signals)                  # plain Python, no model
    scored = [score(s, vertical) for s in signals]
    qualified = [s for s in scored
                 if not s.disqualified_by
                 and s.score >= vertical.qualify_threshold]
    qualified = qualified[:vertical.daily_research_budget]
    leads = []
    for s in qualified:
        research = research_company(s, vertical)
        draft = draft_email(s, research, vertical)
        lead = assemble_lead(s, research, draft)
        store.save(lead)
        leads.append(lead)
    deliver(leads, vertical)
    return leads
```

This is the full orchestration. There are no loops, no re-planning, no agent deciding what happens
next. A human can trace the run from top to bottom in one read.

---

## 6. Agent implementations

### Extractor (`agents/extractor.py`)

Input: `RawItem` + vertical context (ICP description only — no scoring rules).
Output: `Signal | None`.

System prompt emphasises literal reading: extract what is stated, do not infer quality. The
`poster_role` field is classified here (driver vs decision-maker) because it is the same
literal-reading operation as pulling fleet size — not a quality judgment.

Returns `None` (logged, not raised) if `is_company_identifiable` is False after extraction.

### Scorer (`agents/scorer.py`)

Input: `Signal` + the vertical's `scoring_rules` and `disqualifiers` (serialised as a numbered list).
Output: `ScoredSignal`.

System prompt: apply each rule in order, emit the delta for each rule that fires, sum to a score,
check disqualifiers first. The prompt does **not** ask for `why_now` prose — that belongs to the
Drafter. The Scorer emits `reasoning` for the log, not for the reviewer.

### Researcher (`agents/researcher.py`)

Internally two calls:
1. **Search turn** — given `Signal` + product brief, generates 2–3 search queries, executes them
   via the Anthropic web search tool, returns raw notes.
2. **Extraction turn** — given only the notes (never the raw search results), extracts
   `ResearchBrief`. No web access in this turn.

This is the context-isolation principle applied inside one agent. The extraction turn never sees
HTML.

### Drafter (`agents/drafter.py`)

Input: `Signal` + `ScoredSignal` + `ResearchBrief` + product brief.
Output: `EmailDraft`.

The only agent that writes prose a human reads. Uses `confidence` from `ResearchBrief` to calibrate
length: low confidence → shorter email, fewer claims. Does not invent facts not present in the
research brief.

---

## 7. Collectors

### Base protocol (`collectors/base.py`)

```python
class Collector(Protocol):
    def fetch(self, vertical: VerticalConfig) -> list[RawItem]: ...
```

Each collector implements `fetch`. The pipeline calls `collect_all`, which calls `fetch` on every
enabled collector and merges results. A collector that raises is logged and skipped; the pipeline
continues with whatever other collectors returned.

### Job boards (`collectors/job_boards.py`) — Phase 1

Use the Indeed/Workopolis public search pages via Playwright. Collect title, company name, location,
posting date, and full description. Return `RawItem` with `channel="job_boards"`.

Rate-limit to one request per 3 seconds. Respect `robots.txt`. Alert (log + Slack) on zero-yield
runs — a yield drop to zero is almost always a scraper-breaking layout change, not a genuine signal
absence.

### Registry (`collectors/registry.py`) — Phase 2

Federal Motor Carrier Safety Administration (FMCSA) operates a public search for US authority
grants. Transport Canada's NSC database has a search interface. Both are structured; prefer API
endpoints over HTML where available.

`signal_type = "authority_grant"` for these items.

### Reddit (`collectors/reddit.py`) — Phase 3

Official Reddit API, script-type OAuth app. Do not scrape HTML.

Target subreddits: `r/Truckers`, `r/TruckingIndustry`, `r/canadiantruckers`. Search for
`eManifest`, `customs paperwork`, `CBSA`, `dispatch software`, `TMS`.

`poster_role` classification is highest-stakes here: a driver complaint is noise; an owner or
ops manager complaint is a signal. The Extractor handles this — the collector just returns raw posts.

---

## 8. Deduplication (`dedupe.py`)

Two passes, both pure Python:

**Pass 1 — exact signal key**
```python
key = sha256(f"{canonical(company)}:{signal_type}:{evidence[:80]}".encode()).hexdigest()
```
Catches reposts and cross-channel duplicates of the same event. Key stored in `dedupe_keys` table.

**Pass 2 — fuzzy company + 30-day cooldown**
Normalise: strip punctuation, strip corporate suffixes (`Ltd`, `Inc`, `Corp`, `LP`, `LLC`, `Co`),
lowercase. Compare against all companies in the leads table in the last 30 days using
`SequenceMatcher` at threshold 0.82, plus a first-token exact match rule for initialisms.

If match found: drop the incoming signal and log the collision.

**Known gap:** divergent trade names (e.g. "Polar Bear Express" operating as "PBX Transport") still
slip through. Domain resolution via Clearbit or similar would fix this; deferred to Phase 5.

---

## 9. Storage (`store.py`)

SQLite schema for Phase 1:

```sql
CREATE TABLE leads (
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

CREATE TABLE dedupe_keys (
    key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE llm_calls (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    agent TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    latency_ms INTEGER,
    lead_id TEXT,
    created_at TEXT NOT NULL
);
```

`store.py` exposes `save(lead)`, `update_status(lead_id, status)`, `recent_companies(days)` (for
dedupe), and `pending_leads()` (for delivery). When migrating to Supabase, replace this file only —
the interface stays the same.

---

## 10. Delivery (`delivery.py`)

Sends a Slack message per qualified lead via webhook. Format:

```
*[Company name]* — [location] — score [N]/100
*Why now:* [why_now from EmailDraft]
*Evidence:* "[verbatim evidence sentence]"
*Draft subject:* [subject]
[View full draft] [Approve] [Reject]
```

"Approve" and "Reject" are Slack interactive buttons. For Phase 1 these call a minimal webhook
endpoint (a small FastAPI app or a simple serverless function) that calls `store.update_status`.
Full Next.js approval UI is Phase 5.

---

## 11. Eval harness (`evals/`)

### Fixtures (`evals/fixtures/hauler_ai.jsonl`)

50 `RawItem` objects with hand-assigned ground truth, covering:
- 15 clean hiring signals (decision-maker confirmed, fleet size known)
- 10 registry filings (authority grant, company identifiable)
- 10 driver complaints (should score low or be classified driver-role)
- 10 ambiguous items (fleet size unknown, role unclear)
- 5 hard disqualifiers (owner-operator, modern TMS user)

Each line:
```json
{"raw": {...RawItem fields...}, "expected_score": 72, "expected_disqualifier": null, "notes": "..."}
```

### Runner (`evals/run_evals.py`)

For each fixture: run Extractor → Scorer, capture `ScoredSignal`. Compute:
- **MAE** — mean absolute error between `expected_score` and `score`, on non-disqualified items
- **Disqualifier recall** — fraction of expected disqualifiers correctly caught
- **False positive rate** — fraction of items above threshold that a human labelled disqualifiers

Write results to `evals/results/YYYY-MM-DD.json`. Diff against the previous run to catch
regressions.

**Exit criteria (Phase 0):** MAE ≤ 12, disqualifier recall = 100%.

Run the eval harness before every prompt change. Not after — before.

---

## 12. Engineering sequence

| Step | What | Phase |
|---|---|---|
| 1 | `models.py` — all Pydantic types | 0 |
| 2 | `llm.py` — `structured()` wrapper with SQLite logging | 0 |
| 3 | `config.py` + `verticals/hauler_ai.yaml` | 0 |
| 4 | `agents/extractor.py` + prompt | 0 |
| 5 | `agents/scorer.py` + prompt | 0 |
| 6 | `evals/fixtures/hauler_ai.jsonl` — hand-label 50 items | 0 |
| 7 | `evals/run_evals.py` — runner and reporting | 0 |
| 8 | Tune Extractor + Scorer prompts until exit criteria met | 0 |
| 9 | `collectors/job_boards.py` — Playwright scraper | 1 |
| 10 | `dedupe.py` | 1 |
| 11 | `store.py` — SQLite schema + interface | 1 |
| 12 | `pipeline.py` — wire steps 9–11 together, no Researcher yet | 1 |
| 13 | `agents/researcher.py` — two-call internal structure | 1 |
| 14 | `agents/drafter.py` | 1 |
| 15 | `delivery.py` — Slack card, interactive buttons, status webhook | 1 |
| 16 | End-to-end run, deliver to private Slack channel | 1 |
| 17 | `collectors/registry.py` — FMCSA + NSC feeds | 2 |
| 18 | Cross-channel dedupe validation | 2 |
| 19 | `collectors/reddit.py` — OAuth API | 3 |
| 20 | Poster-role accuracy eval (30-item hand-label) | 3 |
| 21 | Approve and send through Instantly; record outcomes | 4 |
| 22 | Reply-rate measurement, scoring retune from evidence | 4 |

Steps 1–8 are Phase 0. Do not start step 9 until exit criteria from step 8 are met.

---

## 13. Environment and dependencies

```
anthropic>=0.40
pydantic>=2.0
playwright>=1.40
python-dotenv
requests
praw          # Reddit API (Phase 3)
fastapi       # approval webhook (minimal, Phase 1)
uvicorn
pytest
```

`.env.example`:
```
ANTHROPIC_API_KEY=
SLACK_WEBHOOK_URL=
REDDIT_CLIENT_ID=      # Phase 3
REDDIT_CLIENT_SECRET=  # Phase 3
```

No credentials management library yet — that is Phase 5 (Nango or Composio).

---

## 14. What not to build yet

- Next.js approval UI (Phase 5)
- Supabase migration (Phase 5)
- Inngest / Trigger.dev durability layer (Phase 5)
- Multi-tenancy / RLS (Phase 6, when a paying customer arrives)
- Compiler agent (Phase 5 — hand-write `hauler_ai.yaml` until then)
- Any second vertical (Phase 5, after Phase 3 exit criteria confirmed)
- Dispatcher and Responder (Phase 7 — see `08-outbound-and-content-pipelines.md`)
- Content pipeline: Planner, Director, Generators, Reviewer, Publisher (Phase 8)

**Never:** voice agents, SMS prospecting, auto-posting to community platforms, or any autonomy
toggle that removes per-message approval. Rationale in `08`.

CRM write-back and email infrastructure stay out of scope — Roxi produces recommendations and the
Dispatcher hands approved items to tools that already exist.
