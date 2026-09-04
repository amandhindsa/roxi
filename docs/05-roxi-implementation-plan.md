# Roxi — implementation plan

Sequenced so each phase produces evidence about whether the next one is worth doing.

Revised 3 September 2026 — phase numbering changed after the outbound and content pipelines were
scoped. Engineering detail for phases 0–4 lives in `07-roxi-technical-build-plan.md`.

---

## The shape of this plan

**Phases 0–3 are about six weeks and answer the only question that matters.**
**Phases 4–8 are roughly six months and are execution against a proven premise.**

Do not interleave them. Every phase has an exit gate stated as a number, and the gates exist to be
enforced rather than admired.

---

## Phase 0 — Eval harness

**This comes before any collector, any prompt tuning, any pipeline.**

50 hand-scored fixtures covering the real distribution: clean hiring signals, decision-maker
complaints, driver complaints, registry filings, ambiguous items, hard disqualifiers. A runner that
scores all 50 and reports mean absolute error, disqualifier recall, and false-positive rate.

*Exit:* MAE ≤ 12, disqualifier recall 100%.

*Why first:* without it every prompt change is a guess, and prompt drift is what kills these
systems around month three. Fifty Haiku calls costs pennies to run.

*Effort:* ~2 days.

---

## Phase 1 — One collector, end to end

Job boards only. Cleanest to collect, strongest hiring signal, lowest legal risk. Full pipeline
daily against real data, cards to a private Slack channel, every card reviewed by hand.

*Exit:* 10+ qualified cards per week, and you agree with the score at least 70% of the time.

*The failure mode here* is adding a second channel instead of fixing scoring. More sources feels
like progress and is not.

---

## Phase 2 — Registry filings and dedupe under load

NSC and US authority-grant feeds. Structured, low-noise, highest intent.

The second channel is where cross-channel duplicates first appear — the same carrier surfacing in
a job posting and a filing in the same week.

*Exit:* no company reaches Slack twice in 30 days.

---

## Phase 3 — Manual send, measure replies

You approve and send through the existing warmed Instantly domain. No Dispatcher — you are the
Dispatcher. Record sent and replied against each lead.

*Exit:* reply rate above 8% on approved sends.

### This is the decision point

If Phase 3 fails, nothing below matters. A reply rate matching generic outbound means the "why now"
is not adding value, and the answer is to stop and reconsider the premise — not to add channels,
not to build the Compiler, not to improve the drafting prompt.

**Everything from Phase 4 onward assumes Phase 3 passed.**

Reddit was originally Phase 3 and has moved after the send test. It is the noisiest channel and
should not be built before the premise is validated.

---

## Phase 4 — Trace table

Every step writes a row: run id, org id, agent, prompt version, input hash, output, tokens, latency,
cost, outcome. No UI yet.

Retrofitting this is painful; adding it while still single-tenant is trivial. Prompt version on
every row is what later answers "did quality drop from my prompt change or from a source changing
its markup".

Reddit collector lands here too, with its own gate: poster-role classification correct on 90% of a
hand-labelled 30-post sample.

---

## Phase 5 — Compiler and second vertical

Build the Compiler agent (`06`, `08`). Prove the config abstraction holds.

*Exit:* a vertical you did not hand-write produces qualified leads with **zero code changes**. If
it needs a code change, the abstraction is wrong — fix the abstraction rather than forking.

Also in this phase: Next.js approval UI, Supabase migration, durable execution layer.

Candidate second verticals: HVAC and trades (SysBuddies), realtors (Magnate360 / WRCIP).

---

## Phase 6 — First paying customer

Multi-tenancy with RLS, tenant-facing run view, per-org spend caps, kill switch, allowlists,
`consent_basis` on contacts.

**Legal review of CASL obligations before this ships, not during.** See `08` §2.

*Exit:* three paying customers in one vertical, each approving more than 60% of surfaced leads.
Approval rate is the real quality metric; everything else is vanity.

---

## Phase 7 — Dispatcher and Responder

Email adapter only. One channel-agnostic reply classifier. Unsubscribe intent writes to the
suppression list immediately.

*Exit:* reply classification correct on 90% of a hand-labelled sample.

Not built: SMS prospecting, voice calls. Call briefs instead of a voice agent. Rationale in `08`.

---

## Phase 8 — Content pipeline

Planner, Director, Generators, Reviewer, Publisher. Text first, then image, then video.

Video last, because it is the only one that forces new infrastructure: its own job queue, per-asset
spend caps, resumable stages. Evaluate HyperFrames before building the assembly stage.

Never: auto-posting to Reddit, LinkedIn, or any community platform.

---

## Cost model

Assume 400 raw items per day, one vertical.

| Stage | Volume | Model | Approx daily |
|---|---|---|---|
| Extract | 400 | Haiku | $0.40 |
| Score | ~250 | Haiku | $0.25 |
| Research | 15 | Sonnet + search | $1.50 |
| Draft | 15 | Sonnet | $0.30 |
| **Total** | | | **~$2.50/day** |

Roughly $75/month per vertical against $299–$599 pricing. Margin is not the constraint.

Without the threshold gate the same volume runs closer to $40/day — which is the entire argument
for the gate, and why loosening it is a cost decision rather than a quality one.

---

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Reply rates match generic outbound | **Existential** | Phase 3 finds this out early and cheaply |
| Scope creep past Phase 3 before validation | **Existential** | Hard phase gates; see below |
| Scraper decay | High | Prefer official APIs; alert on zero-yield runs |
| Company-name resolution failures | High | Fuzzy match plus 30-day cooldown; domain resolution in Phase 5 |
| Hallucinated research facts | High | Mandatory verbatim evidence; confidence field; approval gate |
| CASL exposure once Roxi sends | High | Consent basis per contact; legal review before Phase 6 |
| Brand damage from community posting | High | Publisher never posts to Reddit or LinkedIn |
| Prompt drift | Medium | Phase 0 harness run before every prompt change |
| General agent products absorb the category | Medium | Compete on encoded vertical knowledge, not builder generality |

### The scope risk, stated plainly

Roxi is one of several concurrent ventures — Hauler AI, Magnate360, WRCIP, FieldFlow, SysBuddies,
the driving academy work. The failure mode is not technical. It is building phases 5–8 in month two
because designing systems is more enjoyable than sending forty emails and counting the replies.

The phase gates exist to make that visible when it happens.

---

## The next single action

Build the 50-item fixture set with hand-assigned scores. Everything else is guessing until it
exists.
