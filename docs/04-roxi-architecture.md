# Roxi — architecture and design

---

## 1. Principles

1. **Orchestration is plain code.** No agent decides what happens next. The pipeline is
   a readable sequence of steps that a human can trace.
2. **One decision type per model call.** If two outputs would pull the model in
   opposite directions, they belong in different calls.
3. **Context isolation.** Each agent sees the minimum it needs. The scorer never sees
   raw HTML.
4. **Typed handoffs.** Steps pass validated objects, never chat history.
5. **Evidence or it did not happen.** Every claim carries a verbatim source sentence.
6. **Cheap models filter, expensive models judge.** Gate hard between the two.
7. **Nothing sends itself.**

### The reliability arithmetic

Five sequential steps at 90% each is 59% end to end, with no visibility into which step
failed. Split into independently retried steps at 99% each and you get 95% overall,
plus a trace. This is the entire case for the multi-agent split.

---

## 2. Layer model

```
  Collectors        →  raw items, zero interpretation
  Extractor         →  typed Signal            (Haiku)
  Dedupe + filter    →  plain code, no model
  Scorer            →  ScoredSignal            (Haiku)
  ── threshold gate ──  only qualified pass
  Researcher        →  ResearchBrief           (Sonnet + web search)
  Drafter           →  EmailDraft              (Sonnet)
  Delivery          →  Slack card, human approval
  Outcome capture   →  sent / replied, feeds retuning
```

The gate is the cost lever. Extraction and scoring run on everything at Haiku prices.
Research and drafting run on the qualified minority at roughly 20× the unit cost.

---

## 3. Agent contracts

| Agent | Input | Output | Tools | Model |
|---|---|---|---|---|
| Extractor | `RawItem` | `Signal` | none | Haiku |
| Scorer | `Signal` + ICP rules | `ScoredSignal` | none | Haiku |
| Researcher | `Signal` + product brief | `ResearchBrief` | web search | Sonnet |
| Drafter | all of the above | `EmailDraft` | none | Sonnet |

Only the Researcher gets tools. Giving a model twelve tools produces wrong tool
selection; giving it one produces correct behaviour.

### Boundary decisions worth defending

**The Extractor classifies `poster_role` but makes no quality judgment.** Reading
whether a forum poster is a driver or an owner is the same literal-reading operation as
pulling out a fleet size. Deciding whether the lead is good is not.

**The Scorer emits no prose a human reads.** It returns a score, the list of rules
fired with numeric deltas, internal reasoning, and any disqualifier. It does not write
`why_now`. Scoring wants skepticism; copywriting wants enthusiasm. Coupling them biases
scores upward, because once a model has composed a persuasive line it has committed to
the lead being good. `why_now` belongs to the Drafter.

`rules_fired` also makes the arithmetic checkable: if the model claims 75 and lists
deltas summing to 50, that shows up in the log.

**The Researcher is internally two calls.** A search turn that browses, then a clean
extraction turn that sees only the research notes — never the raw search results. Same
context-isolation principle applied inside one agent.

---

## 4. Data model

```
RawItem      channel, source_url, fetched_at, title, body

Signal       company, company_domain, location, fleet_size,
             signal_type, signal_date, evidence, poster_role,
             is_company_identifiable

ScoredSignal score (0-100), rules_fired[], reasoning, disqualified_by

ResearchBrief company_summary, fleet_estimate, operating_lanes,
             current_stack_guess, decision_maker_title, hooks[], confidence

EmailDraft   why_now, subject, body, hook_used

Lead         raw + signal + scored + research + draft + dedupe_key
```

`evidence` is the load-bearing field. It grounds the model, makes the Slack card
credible to the reviewer, and surfaces hallucination immediately.

`confidence` on the research brief exists so the Drafter can write a shorter email
rather than padding with invention.

---

## 5. Structured output

Every model call uses tool-use with a Pydantic-generated JSON schema and
`tool_choice` forcing the emit tool. Validation failure triggers one retry with the
error fed back as a tool result, then the record is dropped and logged. No regex on
model output, ever.

All calls route through a single `structured()` function so token usage, cost, and
tracing are captured in one place.

---

## 6. Deduplication

Two-stage, both in plain code:

1. **Exact signal key** — SHA of canonical company name + signal type + evidence
   prefix. Catches reposts and cross-channel duplicates of the same event.
2. **Fuzzy company match with cooldown** — normalise the name (strip punctuation and
   corporate suffixes), then compare against companies seen in the last 30 days using
   sequence similarity at 0.82, plus a first-token rule for abbreviations.

This collapses "Northbound Logistics Ltd" and "NORTHBOUND LOG INC" while leaving
unrelated carriers alone. Emailing the same operations manager three times is the
failure that costs a deal, and name variance is the usual cause.

**Known gap:** genuinely divergent trade names still slip through. Domain resolution
would fix it properly.

---

## 7. Stack

| Concern | Choice | Note |
|---|---|---|
| Orchestration | Python, plain sequential code | Move to Inngest or Trigger.dev for durability |
| Models | Claude Haiku 4.5 / Sonnet 5 | Configured per-agent in vertical YAML |
| Storage | SQLite now → Supabase Postgres | RLS required before multi-tenant |
| Scrapers | Python + Playwright | Reuse existing Playwright experience |
| Credentials | Buy — Nango or Composio | OAuth refresh is months of undifferentiated work |
| Delivery | Slack webhook | Approval UI in Next.js later |
| Sending | Existing tools (Instantly, HubSpot) | Roxi never sends |

**Do not run agent loops in serverless functions.** Step-level checkpointing, retries,
and multi-minute timeouts are required. This is the first thing to move off plain
Python once it works.

---

## 8. Configuration as the product

A vertical is one YAML file: product brief, ICP description, explicit additive scoring
rules with numeric deltas, qualify threshold, daily research budget, channels, and
model assignments per agent.

Scoring rules are stated rules with deltas, not descriptions of preference. Models
apply stated rules far more consistently than they infer taste, and it means scoring
can be retuned without touching a prompt.

**No vertical-specific logic in code. Ever.** The moment a carrier-specific rule leaks
into `pipeline.py`, the platform thesis is dead.

---

## 9. Multi-tenancy — deferred, not ignored

When a second customer arrives: per-org rows with RLS, per-org credential scoping,
per-org allowlists of what the agents may touch, per-org cost caps, and audit logging
of every tool execution with org context. Design the schema for this now; build it when
a paying customer requires it.
