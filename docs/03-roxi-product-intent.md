# Roxi — product intent

---

## 1. The problem

Small B2B companies with no marketing headcount know who they should be selling to but
have no reliable way to find those companies at the moment they become buyable.

The available options all fail differently:

- **Buy a list** — static, no timing, everyone else bought the same list
- **Hire an SDR** — $60–90k plus ramp, and most of the job is research
- **Use Clay or Apollo** — excellent enrichment, but you must already know who to enrich
- **Use Zapier or a general agent** — you design the entire system yourself

The research half of the SDR job — figuring out *who*, *why now*, and *what to say* —
is the expensive part and the automatable part. Sending and closing are not.

---

## 2. What Roxi is

**Roxi finds companies that just became buyable, explains why, and drafts the opener.**

It runs on a schedule, monitors channels appropriate to a vertical, applies an explicit
ICP rule set, and produces a reviewable card: the company, the evidence, why now, and
a draft email. A human approves. Sending happens in tools already owned.

### The positioning line

> Roxi replaces the research half of an SDR. You keep the conversation.

---

## 3. What Roxi is deliberately not

- **Not a workflow builder.** The opinionated playbook is the product. If a customer
  wants to design their own automation, they should use Zapier or Claude Cowork.
- **Not a sender.** No mail infrastructure, no deliverability problem, no domain
  reputation risk, no CAN-SPAM/CASL exposure from automated sending.
- **Not a CRM.** It writes into whatever CRM already exists.
- **Not autonomous.** Nothing leaves the system without a human clicking. This is a
  product principle, not a limitation to be engineered away later.

Each of these is a deliberate scope refusal. Rilo's failure mode was breadth at six
people; Roxi's constraint is depth in one vertical at a time.

---

## 4. Beachhead: Hauler AI / Canadian carriers

The first vertical is one where the domain knowledge is already in the building.

**ICP:** Canadian trucking carriers, 10–100 power units, cross-border freight.

**Signals that indicate buyability:**
- New or expanded US operating authority (about to hit cross-border paperwork volume)
- Hiring a dispatcher, safety officer, or fleet manager (ops strain, budget exists)
- Public complaint about manual eManifest entry or a legacy TMS (named pain)

**Disqualifiers:** under 8 trucks, owner-operators, asset-free brokers, US-domiciled
carriers with no Canadian operations, anyone already on a modern TMS.

**Why this vertical first:** the signals are public and structured (registry filings,
job postings), the pain is specific and quantifiable (hours per week rekeying customs
data), the buyer is reachable, and there is an existing product to sell.

### Vertical two and three

Once the engine works, a vertical is a YAML file: ICP description, scoring rules,
channels, product brief. Candidates already in reach — HVAC and trades contractors
(SysBuddies), and realtors (Magnate360 / WRCIP, where proprietary property signals
would be a genuine moat).

**Rule: do not open vertical two until vertical one produces measured reply-rate lift.**

---

## 5. Why this can win where Rilo could not

| Rilo | Roxi |
|---|---|
| Any workflow, any industry | One vertical, deeply encoded |
| User defines what "good" means | Roxi ships knowing what good means |
| Competes with Claude Cowork | Competes with hiring an SDR |
| Value in the builder | Value in the rule sets and channel knowledge |
| Free tier, 10k users, no revenue | Paid from first customer, few customers |

The moat is not technical. Anyone can wire four Claude calls together. The moat is
the accumulated, tested knowledge of which signals actually predict a reply in a given
vertical — which only comes from running the loop and measuring outcomes.

---

## 6. Business model

**Pricing hypothesis:** $299–$599/month per vertical. Priced against an SDR's salary,
not against Zapier's.

Deliberately no free tier. Offer a paid two-week pilot with a fixed lead volume.
Rilo's free-first-workflow model produced 10,000 users and an acquihire.

**First revenue path:** run it for Hauler AI internally. If it produces qualified
conversations, that becomes both the case study and the proof the engine works before
a single dollar of outside customer money.

---

## 7. Success criteria

**Phase 1 (internal, 6 weeks)** — 15 qualified leads per week for Hauler AI, with a
reply rate above 8% on approved sends. Below that, the scoring is wrong and no amount
of engineering fixes it.

**Phase 2 (design partners, 3 months)** — three paying customers in one vertical, each
approving more than 60% of surfaced leads. Approval rate is the real quality metric;
everything else is vanity.

**Kill criteria** — if reply rates match generic outbound, the "why now" is not
actually adding value and the premise is wrong. Stop and reconsider rather than adding
channels.
