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
| `08-outbound-and-content-pipelines.md` | Dispatcher, Responder, and the content pipeline. Nothing here is built |

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

- Working prototype: four agents, Hauler AI vertical, fixtures only.
- No collectors wired to live sources. No eval harness. **The eval harness is the next action.**
- Compiler, Dispatcher, Responder, and the content pipeline are specified but unbuilt.

## Source discipline

`01` and `02` distinguish three tiers throughout:

- **Confirmed** — Rilo's own site, careers page, or published materials
- **Reported** — press coverage of the acquisition
- **Inferred** — reasoning from the observable product surface, explicitly labelled

Do not let inference harden into fact through repetition in later documents.

## Legal note

`08` describes CASL and CRTC obligations that attach the moment Roxi sends on a customer's behalf.
That summary is orientation, not legal advice. Get real advice before Phase 6.
