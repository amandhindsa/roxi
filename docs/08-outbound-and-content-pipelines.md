# Roxi — outbound and content pipelines

The GTM run (`04`, `06`) ends at a drafted email awaiting approval. This document covers what
happens after that, and the parallel content pipeline.

Compiled 3 September 2026. **Nothing here is built. Phases 7–8 in `05`.**

---

## 1. The rule that governs both pipelines

Split components when the **decisions** differ, not when the channel or media type differs.

Channel is usually a parameter. Media type usually changes only cost and latency — which changes
*where the approval gate sits*, not how many agents you need.

Applied consistently, this produces far fewer components than the instinct to break things down by
category. Three near-identical prompts that drift apart are worse than one prompt with a parameter.

---

## 2. Outbound: Dispatcher and Responder

### Dispatcher — code, no model

Sending is not an LLM job. It is an adapter plus a queue: rate limits, retries, bounce handling,
suppression lists, audit rows. Adding a model here introduces nondeterminism at the one step that
must be deterministic.

One interface, per-channel implementations:

| Adapter | Handles |
|---|---|
| Email | Bounces, suppression, sending domain reputation, threading |
| SMS | Segment splitting, carrier filtering, opt-out keywords |

The Dispatcher executes **only** items a human has already approved. It has no judgment and no
discretion. It checks consent basis per channel before every send, and the suppression list is
enforced in this layer so no upstream agent can bypass it.

### Responder — one agent, not three

Reply classification is channel-agnostic. "Not interested" is the same intent by email or text.
One classifier, one eval set, one prompt.

- **Input:** inbound message + the original lead context
- **Output:** intent (interested, not now, wrong person, out of office, unsubscribe, hostile),
  extracted details (referral name, timing), suggested next action
- **Unsubscribe intent writes to the suppression list immediately**, before any human sees it

Drafting the follow-up is channel-*shaped* but that is a parameter passed to the existing Drafter
— 160 characters and no links for SMS, longer with a signature for email. Not a new agent.

The Responder also closes the measurement loop: reply outcomes are what let scoring rules be
retuned against evidence rather than intuition.

### Calls — deliberately not built

A voice agent is real-time and sub-second, with no possible approval gate mid-conversation. The
human-in-the-loop principle evaporates the moment it dials, and it is the highest-blowback surface
in the system.

**Instead:** Roxi produces a **call brief** — who, why now, the hooks, likely objections drawn from
the research — and a human dials. All of the research value, none of the autonomous-system risk.

### Compliance divergence by channel

This is the substantive reason the adapters are separate, and it is jurisdiction-specific. Roxi
operates from BC selling into Canada, so CASL and CRTC rules govern.

- **Email** — CASL requires express or implied consent *before* sending, unlike US CAN-SPAM which
  is unsubscribe-after. Implied consent from a conspicuously published business address exists but
  is narrow and time-limited. Identification and a working unsubscribe are mandatory in every
  message. This is the only channel with a viable cold path.
- **SMS** — express consent, in practice. The implied-consent route that makes cold email workable
  is much weaker here. Treat SMS as a customer-communication channel, not a prospecting one.
- **Calls** — CRTC telemarketing rules: National DNCL registration and subscription, calling-hour
  restrictions, mandatory identification. Recording adds notification duties.

Penalties under CASL reach $10M for organisations. **Get real legal advice before customer one.**
Nothing in this document is legal advice.

Architectural consequence: `consent_basis` is a field on the contact, checked by the Dispatcher per
channel, and the suppression list sits below every agent.

---

## 3. Content: Planner, Director, Generators, Reviewer, Publisher

Generation is not an agent. It is a tool adapter with retries.

| Stage | Type | Job |
|---|---|---|
| Planner | Agent | Decides what to say this week per channel, from the brand brief and source material |
| Director | Agent | Writes the production brief — image prompt, video script and shot list, or post copy |
| Generators | Adapters, no model | Call image, video, and voice services. Deterministic, with retries |
| Reviewer | Agent | Checks the finished asset against brand rules and claim substantiation |
| Publisher | Code, no model | Posts to platform APIs. Rate limits, formats, scheduling, audit rows |

### The Reviewer is the stage people skip

It is the same skeptic-versus-enthusiast split as Scorer and Drafter. The Director wants the asset
to be compelling; the Reviewer asks whether the claim in it is supportable and whether it matches
brand rules. Opposite dispositions, so they must be different calls.

### Text and video have different gates

**Text:** approve the *output*. Generation is instant and effectively free, so regeneration is cheap
and the human reviews the finished thing.

**Video:** approve the *input*. A minute of generated video costs dollars and minutes across a
multi-stage chain — script, voiceover, shots, assembly. A human signs off on the Director's brief
before a single generation call fires. Same threshold-gate logic as the research stage, applied to
a different scarce resource.

Consequence: video needs its own async job queue with per-asset spend caps, resumable stages, and a
state machine. It is not a step in the daily run. A failed assembly at stage four must not re-run
the voiceover.

### Build order

Text, then image, then video. Video last because it is the only one that forces new infrastructure.

**Note:** HyperFrames (already connected in the working environment) handles the script-to-rendered-
video chain and would remove the need to build the assembly stage. Evaluate before building.

### Platform posting is uneven

Image and text posting APIs exist for most platforms. Video posting is more restricted, and some
platforms do not permit programmatic posting at all. Verify per platform before promising coverage
— the Publisher's reach constrains what the Planner can propose.

### What the Publisher must never do

- **Auto-post to Reddit.** Promotional automation violates Reddit's rules and most subreddit rules.
  An agent replying in threads is the fastest possible way to destroy the brand, permanently and
  searchably. Reddit stays read-only for discovery; a human posts.
- **Automate LinkedIn.** Violates their user agreement and risks account restriction.

---

## 4. Autonomy ladder

| Component | Type | Autonomy |
|---|---|---|
| Compiler | Agent | Proposes config; human edits and confirms |
| Extractor, Scorer | Agents | Fully automatic — output is internal, nothing external happens |
| Researcher, Drafter | Agents | Fully automatic — output queued for approval |
| Dispatcher | Code | Executes approved items only |
| Responder | Agent | Classifies automatically; follow-ups require approval |
| Planner, Director | Agents | Propose; human approves brief before generation spend |
| Generators | Adapters | Run on approved briefs, under spend caps |
| Reviewer | Agent | Automatic pre-screen; never the final approver |
| Publisher | Code | Posts approved assets only; never to community platforms |

**Approval is per-message, not a mode.** There is no "fully autonomous" toggle, because the instant
one exists somebody enables it and the first bad send lands on a customer's domain.

---

## 5. Explicit non-goals

- Voice agents that place calls — call briefs instead
- SMS prospecting — SMS is for existing customer relationships
- Auto-posting or auto-replying on Reddit, LinkedIn, or any community platform
- CRM write-back and email infrastructure — Roxi produces recommendations; existing tools send
- Any autonomy toggle that removes per-message approval
