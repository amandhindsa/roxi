# Roxi — multi-customer operations and the customer UI

A design document for turning Roxi from a tool one person runs into a service customers subscribe
to, across any number of industries.

Written 4 September 2026. Nothing in here is built yet.

---

## 1. Where we are today

Honest starting position, from reading the code.

**What works.** The daily pipeline runs end to end. Rules for who counts as a good lead are already
separated from the software — they live in configuration files, and two industries are described
that way today: Canadian trucking carriers and HVAC and trades contractors. Every model call is
recorded with its cost. There is a working approval screen showing each lead with its evidence, the
rules that fired, the research, and the draft email, plus a control dashboard with health checks,
funnel numbers, a cost chart, and a live event log.

**What is missing for customers.**

- **Nobody logs in.** The interface has no sign-in and no concept of who is looking at it. Anyone
  who can reach the address sees everything.
- **The rules live inside the software.** They ship in the codebase, so only we can change them, and
  changing a single number requires a new release.
- **Leads are not separated by customer.** Roxi remembers which companies it has surfaced, but not
  who it surfaced them for.
- **The interface assumes one industry.** It displays "units" and "lanes" — vocabulary from
  trucking — and defaults to the trucking rule set when no other is specified.
- **Nothing is scheduled.** Runs are started by hand.

None of this is a design flaw. It is what a working single-customer system looks like. The rest of
this document is the work to make it serve many.

---

## 2. What has to change

### A. Customers, and what they subscribe to

The unit of work is not a customer and not an industry — it is the pairing of the two. One customer
may target several industries; one industry may be targeted by several customers.

So we need three new concepts:

- **Organisation** — the customer company. Owns everything else.
- **Member** — a person who can sign in, belonging to one organisation, with a role.
- **Subscription** — an organisation targeting one industry, with its own rules, its own sources,
  its own daily budget, and its own on/off switch.

Everything Roxi produces hangs off a subscription. Every daily run is one subscription's run.

**Roles**, kept deliberately few:

| Role | Can do |
|---|---|
| Owner | Everything, including editing rules, connecting sending, and inviting people |
| Reviewer | Approve and reject leads, view everything, cannot change rules |
| Viewer | Read-only. For a manager who wants the numbers but not the queue |

### B. Rules become customer data, not code

Today a customer's targeting is a file inside our repository. That has to become a record in the
database, owned by the customer, with a version number.

Every edit creates a new version rather than overwriting. Every run records which version it used.

This matters more than it sounds. When a customer asks why Tuesday's leads look different from
Monday's, the answer is almost always that somebody changed a rule. Without versioning that
conversation has no evidence in it. With versioning it is a two-line answer.

It also means a customer can experiment safely: change a threshold, watch a week, change it back.

### C. Separation between customers

Three things need to be kept apart, and only one of them is obvious.

**Their leads.** Straightforward — every lead belongs to a subscription.

**Their memory of who has already been seen.** This is the one that causes real damage if missed.
Roxi avoids surfacing the same company twice, but currently that memory is shared. If two customers
sell into the same industry, the second one silently stops seeing companies the first already
received. Neither would ever know it was happening. Each subscription needs its own memory.

**Their spending.** Each subscription has a daily ceiling, checked before every model call. A
runaway job on one account must not be able to spend another customer's budget or ours.

### D. Sources, per customer

Where Roxi looks differs by industry. Job postings work almost everywhere. Government transport
filings matter for carriers. Building permits matter for trades. Industry forums matter for both,
but different ones.

So sources become a catalogue that customers choose from, in three tiers:

- **Universal** — job postings, news, general web search. Available to every customer on day one.
- **Category** — funding announcements, permit portals, procurement notices, industry registries.
  Cover a whole segment, built once, reused.
- **Bespoke** — a single customer's private data or an unusual public registry. Built only when a
  customer's contract justifies it.

Two practical requirements. Each customer supplies their own access where a source needs an account,
so one customer's usage cannot get everyone else blocked. And **when a source stops returning
anything, somebody must be told** — a silent source looks exactly like a quiet week, and in practice
it usually means the site changed and our reader broke.

### E. Scheduling

One job per subscription per day, handled by a shared pool of workers. No customer needs their own
dedicated machine — a daily run is roughly twenty minutes of work.

Runs must be safe to retry, so a worker dying halfway through does not double-charge or double-send.

Customers pick their delivery time in their own timezone. A morning digest that lands at 3am is not
a morning digest.

### F. Limits that protect everyone

- A daily spend ceiling per subscription, refusing further work rather than overspending
- A cap on how many leads are researched per day, which is already how cost is controlled
- A pause switch per subscription, and a global one for us
- Polite request rates per source, per customer

---

## 3. The customer-facing interface

Yes, this is needed, and it is more than an approval queue. A customer is being asked to put their
name on outbound mail; they need enough visibility to take that responsibility seriously.

Seven screens, plus settings. The first one is where a customer starts before any leads exist.

### 0. Setup — the interview

This is the screen a new owner sees first, and it is the one furthest from what exists today. The
interview currently runs as a terminal program: it prints questions, waits for typed answers, and
ends by printing raw configuration text. A customer can never reach it, and the output is exactly
the syntax the rest of this document says they should never see.

As a screen it works like this:

1. **Two fields to begin.** What do you sell and who buys it, and your website address.
2. **A short conversation.** Roxi reads the site, then asks what it needs. A handful of exchanges,
   not a long form. The questions that carry the most weight are about the negative case — what
   does a *bad* customer look like — because disqualifiers hold most of the accuracy and nobody
   offers them unprompted.
3. **The draft, in plain English.** Not configuration. Something closer to: "We will look for
   companies with 10 to 100 trucks. We will skip owner-operators and anyone already on a modern
   system. A new cross-border authority filing is worth 35 points, hiring a dispatcher 25."
4. **Accept, or say what is wrong.** Corrections are given in ordinary words and the draft is
   rewritten. This loop runs as many times as needed.
5. **Honesty about fit.** If an industry has no publicly observable buying signals, the interview
   should say so rather than produce a configuration that will disappoint. A short honest "this is
   not a good fit for us" costs one sale and saves a refund and a bad reference.

**The technical requirement this creates.** The existing interview holds the whole conversation in
memory and blocks waiting for the next typed line. A screen cannot work that way — each answer
arrives as a separate request, possibly hours apart, possibly from a different device. The
conversation has to be stored against a setup session, appended to with each reply, and resumable,
because people abandon setup halfway through and come back the next day. That is a rewrite of the
interview, not a wrapper around it.

**Run it manually first.** For the first several customers, do the interview live on a call and
fill in the configuration yourself. Watch where they hesitate, where they misunderstand the
question, and where they give an answer the current questions cannot use. Those moments are the
specification for the self-serve version. Building the form before knowing what to ask produces a
polite form that asks the wrong things.

### 1. Today's leads — the core screen

The queue of leads awaiting a decision. This largely exists already: company, location, score, the
one-line reason it matters today, the verbatim evidence quoted from the source, the rules that
fired, and — on expand — the research brief and the draft email.

What it needs adding:

- **Editable drafts.** Reviewers will want to change a sentence before approving. Currently the
  choice is accept or discard.
- **A reason when rejecting.** Not required, but offered: wrong size, wrong industry, already a
  customer, bad timing. This is the highest-value feedback in the entire product, because it is a
  human telling us exactly where the rules are wrong.
- **Keyboard review.** Approve, reject, next. Someone working through fifteen leads should not have
  to reach for the mouse.
- **Neutral vocabulary.** "Units" and "lanes" are trucking words. The label should come from the
  customer's own configuration.

### 2. Lead history

Everything already decided, filterable by status and date, searchable by company. Shows what was
sent, what came back, and when.

### 3. Run history — including what was dropped

Each day's run: how much was collected, how much survived each stage, how many leads were delivered,
what it cost.

The valuable half is **what did not make it and why** — dropped as a duplicate, disqualified by a
named rule, scored below the threshold, or beyond the day's research budget.

This needs the stage-level logging described in `09-known-bugs.md` M7, which does not exist yet.
Until it does, this screen can only show totals. It is worth building precisely because "why didn't
this company show up" is the question customers will actually ask.

### 4. Rules

The customer's own targeting, in plain language: who they sell to, what disqualifies a company, what
signals matter and how much each is worth, and the score at which a lead is worth their attention.

Edited in plain English, never as configuration syntax. Every save creates a version. The history is
visible, and any version can be restored.

**The most useful feature on this screen** is a preview: apply the edited rules to last week's
leads and show what would have changed. Rule editing without that is guesswork.

### 5. Sources

Which sources are on, when each last ran, how much each returned, and a clear warning when one has
gone quiet. Where a source needs the customer's own account, they connect it here.

### 6. Results

Reply rate overall, and reply rate broken down by score band. That second number is the one that
proves or disproves the whole product: if leads scoring 90 reply at the same rate as leads scoring
70, the scoring is not doing anything.

Also: approval rate, which is the honest measure of quality. A customer approving 30% of what they
are shown is being shown too much rubbish.

### Settings

Team members and roles, sending connection, suppression list with manual add and remove, spend
ceiling, delivery time and timezone, notification preferences.

### The operator console stays separate

Our own view — health across all customers, cost per customer, source reliability, evaluation
results, model versions — is a different application with different sign-in.

**It never shows one customer's leads to anyone else.** Aggregate numbers, yes. Another company's
prospect list, never. If two customers ever compete, cross-visibility in our admin screen is a
breach waiting to happen. The boundary goes in before the second customer, not after.

---

## 4. Bringing a customer on

1. **Interview.** They describe their product and their buyer. Roxi reads their website. It asks
   what a *bad* customer looks like, because disqualifiers carry most of the accuracy and nobody
   volunteers them. Early on this happens on a call with us driving; later it is screen 0.
2. **Draft rules.** Presented in plain English for the customer to correct. They know their market
   better than any model does.
3. **Label examples.** Someone marks about fifty real examples with what each is worth. **This is
   the step that cannot be skipped or automated** — it is how we find out whether the rules work
   before anything is sent, and rules tuned for carriers say nothing about contractors.
4. **Check the scoring** against those labels. If it disagrees badly, fix the rules and repeat.
5. **Quiet run.** Several days of real runs with nothing sent. Leads are collected and scored and
   reviewed; no research spend, no outbound. This is the cheapest insurance available — it is where
   targeting mistakes surface, before money or reputation is involved.
6. **Go live.** Sending connected, daily digest on.

Steps 3 to 5 take a few days of calendar time and a few hours of human attention. That is the real
cost of a new industry, and it should be priced in.

**Early on, run this with the customer rather than handing them a form.** Self-serve onboarding is
a later goal; the first several customers teach us what the interview should actually ask.

---

## 5. Implementation plan

Each stage has a condition for moving on. The order is chosen so nothing is built before the thing
it depends on.

### Stage 1 — Identity and separation

Organisations, members, roles, subscriptions. Every lead, every memory of a seen company, and every
run tagged with its subscription. Sign-in on the customer interface.

*Done when:* two accounts running the same industry never see each other's leads, and neither
suppresses the other's.

*Why first:* these are structural changes to how data is stored. They are cheap now and expensive
once there is real customer data to migrate.

### Stage 2 — Rules as customer data

Rules move out of files and into records, with versions. Runs record the version used. A read-only
rules screen so customers can at least see their own targeting.

*Done when:* a rule can be changed without a release, and any past run can be traced to the exact
rules it used.

### Stage 3 — Stage-level logging

Record what happened to every item at every stage, including everything dropped and why.

*Done when:* "why did this company not appear" is answerable with a lookup rather than a guess.

*Why here:* several known defects are silently discarding leads today. Fixing them without this
means fixing them blind, with nothing to compare before and after.

### Stage 4 — Customer interface, first version

Sign-in, today's leads, lead history, run history, results. Editable drafts and rejection reasons.
Vocabulary driven by the customer's configuration rather than hardcoded.

*Done when:* a customer can do their entire daily review without us.

### Stage 5 — Scheduling and limits

Daily runs per subscription, at each customer's chosen time. Spend ceilings enforced. Pause
switches. Alerts when a source goes quiet.

*Done when:* a week passes with no manual intervention and no budget surprises.

### Stage 6 — Self-service rules, sources, and setup

Editable rules with the preview-against-last-week feature. Sources switched on and off by the
customer. The interview becomes a screen: stored conversation, resumable across sessions and
devices, plain-English draft, no configuration syntax anywhere in the customer's view.

*Done when:* a customer completes setup without us on the call, changes their own targeting, sees
the predicted effect, and the next run reflects it.

*Note:* the interview rewrite is the larger half of this stage. Until it ships, onboarding is a
manual step we perform — which is the right sequence anyway, since the first several interviews
teach us what the questions should be.

### Stage 7 — Results and retuning

Reply rates by score band. Rejection reasons fed back into rule suggestions.

*Done when:* we can show a customer that higher-scoring leads genuinely reply more — or discover
that they do not, which is more valuable still.

### Stage 8 — Operator console

Cross-customer health, cost, source reliability, evaluation history. Separate sign-in, no lead data
across boundaries.

*Done when:* a source breaking for one customer is noticed by us before they report it.

---

## 6. Decisions still open

- **Who sends?** Roxi currently hands approved leads to a sending tool. Should customers connect
  their own, or do we host it? Connecting theirs keeps us out of the deliverability and compliance
  business, which is the right call for now, but it is a rougher setup experience.
- **How much of the dropped-item detail do customers see?** It contains scraped third-party
  material. Useful for trust, but it carries privacy retention obligations. Needs a retention period
  decided up front rather than discovered later.
- **Priced per industry or per seat?** Per industry matches the cost structure and the value. Per
  seat is more familiar to buyers.
- **Self-serve or assisted onboarding?** Assisted for the first several customers. The interview is
  where all the learning is.
- **How long is data kept?** Leads, dropped items, and traces all need a stated period, and
  customers need a way to request deletion.

---

## 7. Deliberately not building

- A dedicated deployment per customer. Runs are short and shared workers handle them fine. The only
  real argument for separation is source access, which is solved with per-customer credentials
  rather than per-customer machines. If an enterprise buyer contractually demands isolation, charge
  for it rather than designing around it.
- Sending infrastructure of our own.
- Any way to turn off per-message approval. The moment that switch exists, someone flips it, and
  the first bad message goes out under a customer's name.
- A general workflow builder. Customers configure their targeting; they do not design their own
  pipeline. That was the strategic error identified in `02-rilo-architecture.md`.
