# Roxi — documentation index

Roxi is a go-to-market and brand-building platform: agents that research the open web across
channels, score what they find against a generated ICP, and hand a human a drafted, evidence-backed
outreach recommendation.

Compiled 3 September 2026. Last revised the same day.

## Reading order

| Doc | Purpose |
|---|---|
| `01-rilo-market-research.md` | What Rilo was, how it was funded, why Adobe bought it, and what the market looks like now |
| `02-rilo-architecture.md` | Rilo's system design — confirmed facts separated from inference |
| `03-roxi-product-intent.md` | Why Roxi exists, who it serves, and what it deliberately is not |
| `04-roxi-architecture.md` | System architecture, data model, and agent contracts |
| `05-roxi-implementation-plan.md` | Phases 0–8 with exit gates, cost model, and risk register |
| `06-agent-specifications.html` | Per-agent spec sheet: what each does, does not do, and how it fails |
| `07-roxi-technical-build-plan.md` | Repo layout, module boundaries, interfaces, engineering sequence |
| `08-outbound-and-content-pipelines.md` | Dispatcher, Responder, and the content pipeline |
| `09-known-bugs.md` | Code review of `roxi/` — 22 defects including stage-observability and multi-tenancy sections, severity-ranked, with a fix order |
| `10-how-the-agents-work.html` | How all eleven components behave in the code: call mechanics, the four pipelines, what is model and what is not |
| `11-multi-customer-operations.md` | Turning Roxi into a multi-customer service: separation, rules as data, the customer UI, onboarding, eight build stages |

## The load-bearing decisions

**The agent set is fixed; the config is generated.** Extractor, Scorer, Researcher, Drafter are
domain-independent. A Compiler agent interviews the user and writes the vertical config, so nobody
hand-authors a spec sheet per use case. This makes the platform general while keeping the runtime
narrow — the opposite of Rilo, whose builder compiled arbitrary workflows into an unbounded output
space.

**One decision type per model call.** If two outputs would pull a model in opposite directions they
belong in different calls. Scoring wants skepticism, drafting wants warmth, and coupling them
biases scores upward.

**Compile at setup, execute at run time.** Ambiguity is resolved once, with a person present.
Daily runs execute a frozen, versioned config.

**Nothing sends itself.** Approval is per-message, not a mode. There is no autonomy toggle, because
the moment one exists somebody enables it and the first bad send lands on a customer's domain.

**Phase 3 is the decision point.** Reply rate above 8% or the premise is wrong. Everything from
Phase 4 onward assumes it passed.

## Status

- Codebase is well ahead of this documentation: agents, collectors, Dispatcher, Responder,
  content pipeline, Supabase support, and a Next.js approval UI all exist.
- **The eval harness has never been run.** `evals/results/` and `tests/` are empty, so Phase 0
  exit criteria are unverified.
- 22 known defects logged in `09-known-bugs.md`, two of them blocking today: stale model IDs break
  every Sonnet call, and the job-board collector silently returns one item per query. A further
  seven are latent multi-tenancy issues that activate at customer two.
- **Seven of the eleven ways an item can be dropped leave no database record** (M7). Fix that
  before the dedupe bugs, or their effect cannot be measured.
- **Next action: fix the model IDs, then run the evals to establish a scoring baseline.**

## Source discipline

`01` and `02` distinguish three tiers throughout:

- **Confirmed** — Rilo's own site, careers page, or published materials
- **Reported** — press coverage of the acquisition
- **Inferred** — reasoning from the observable product surface, explicitly labelled

Do not let inference harden into fact through repetition in later documents.

## Legal note

`08` describes CASL and CRTC obligations that attach the moment Roxi sends on a customer's behalf.
That summary is orientation, not legal advice. Get real advice before Phase 6.
