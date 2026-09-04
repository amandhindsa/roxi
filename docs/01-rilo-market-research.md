# Rilo — market research

Compiled 3 September 2026, one day after the acquisition was announced.

---

## 1. Company facts

| | |
|---|---|
| Product domain | getrilo.ai |
| Legal entity | Workatoms, Inc., San Francisco, California |
| Founded | September 2025 |
| Founders | Dhruv Jaglan (CEO), Georgi Boby (CTO) — IIT Bombay batchmates |
| Funding | ~$1M seed at a $10M valuation |
| Investors | Peak XV Partners, DeVC / Z47, Day Zero Ventures |
| Users | 10,000+ within months of launch |
| Team at exit | 6 people |
| Outcome | Acquired by Adobe, announced 2 September 2026 |

Founder backgrounds: Jaglan previously co-founded Babblebots.ai, an AI recruitment
platform. Boby led technology at CloudChef, a cooking-robotics company. The wider team
included IIT Bombay computer science graduates, one of whom placed AIR 2 in JEE
Advanced 2016. This is a strong-technical-team profile, not a strong-distribution one.

**Naming collision worth knowing:** `riloworks.com` is a *different* company under a
similar brand, positioned around "autonomous AI employees" for general knowledge work.
Much of the detailed architecture material circulating online under the name "Rilo"
describes that company, not the one Adobe bought. Third-party comparisons explicitly
distinguish the two. Do not mine riloworks.com for competitive intelligence on the
acquired product.

---

## 2. What the product actually did

Positioning line: *"Your GTM team just got bigger. Without the headcount."*

The pitch was outcome-owned agents rather than trigger-and-action automation — an
explicit shot at Zapier and Make, and a partial one at Clay.

### Shipped workflow templates

Four, each advertised at roughly three minutes of setup:

1. **Competitor digest** — daily summary of competitor launches, reviews, posts, and
   hiring signals, ranked by relevance, delivered to Slack or email.
2. **Pipeline signals** — tracks funding, hiring spikes, and pain signals across the
   customer's ICP. On a trigger, returns the prospect, the context, and a draft email.
3. **Investor tracking** — monitors target VCs and angels across Twitter, blogs,
   podcasts, and portfolio news; surfaces when they discuss your space.
4. **Content repurposing** — takes a LinkedIn post, blog draft, or transcript and
   adapts it into platform-native formats, queued as drafts for review.

Beyond templates, users could describe any workflow in plain English and the system
would ask clarifying questions and build it.

### What customers actually ran

From testimonials on the site: lead enrichment with structured push into a CRM,
inbound qualification, community and support-channel listening, sales call transcript
analysis surfacing objections and buying signals, Slack reporting, onboarding
workflows.

### Reddit and social — a correction worth carrying forward

Press coverage listed "Reddit marketing" and "social media content" as capabilities.
The product surface tells a narrower story: Reddit appeared as a scraper connector
(`RedditScraperTool`), alongside Twitter and Facebook scrapers. There was no dedicated
Reddit lead-generation agent. A competitor's comparison page states plainly that
Reddit was not the centre of Rilo's public product story.

**Implication for Roxi:** the "Reddit marketing" job to be done was real but
underserved. Rilo gave you read access and a workflow builder; you assembled the
motion yourself. A purpose-built Reddit discovery agent is a genuine gap.

---

## 3. Commercials

- Free first workflow, no credit card, first output in ~15 minutes.
- Growth around $99/month, Pro around $299/month (cited from public event materials;
  treat as directional).
- Explicit human-in-the-loop: an FAQ entry specifically addressed whether the system
  would send email or post content without approval.

At $99–$299 with 10,000 users, revenue was almost certainly immaterial. This was a
free-tier-heavy adoption curve, not a revenue business.

---

## 4. The acquisition

Announced 2 September 2026. Structure: technology licensing plus team acquisition.
Adobe integrates some of Rilo's IP and onboards the six-person team. Investors receive
an exit. The standalone product shuts down; existing customers lose access.

Terms undisclosed. Given $1M raised at a $10M valuation and a 12-month timeline, this
was an acquihire with an IP tail — not a strategic outcome. Do not read it as
validation that the product had found product-market fit.

**Adobe's context.** Second Indian acquisition after Rephrase.ai in 2023. It follows
Adobe's $1.9B purchase of SEO platform Semrush in 2025, and their April 2026 launch of
CX Enterprise — an agentic system with AI agents, reusable skills, MCP endpoints, and
a governance layer. Rilo plugs a specific hole: a natural-language workflow builder
that puts agentic automation in the hands of non-technical marketers.

---

## 5. Market read

### Why the category is hot

Competition in AI-powered marketing is intensifying from several directions at once:
Anthropic launching marketing-focused Claude capabilities, Canva acquiring in
marketing automation, and Amazon, Google, and Meta expanding their own AI marketing
tools. Adobe buying a 12-month-old startup for its team is a signal about talent
scarcity in agentic GTM, not about Rilo specifically.

### Where the competitive field sits

- **Horizontal automation** (Zapier, Make, n8n) — reliable, but the user designs
  everything and it is trigger-and-action, not outcome-owned.
- **Data enrichment** (Clay, Apollo) — excellent at enrichment, weak at open-web
  discovery and at judgment.
- **Opinionated AI marketing crews** (Runlo and similar) — fixed agent roles, flat
  pricing, strict draft-first. Directly targeting Rilo's users with a "you shouldn't
  have to design the system" pitch.
- **General agent platforms** (Claude Cowork, ChatGPT Work) — Rilo was described as an
  early Claude Cowork competitor. This is the existential threat: general-purpose
  agent products absorbing the workflow-builder layer.

### The strategic lesson for Roxi

Rilo's flexibility was its differentiator *and* its ceiling. A blank workflow builder
competes directly with general agent products that have vastly more distribution and
better models. The defensible position is the opposite: a narrow, opinionated system
for one vertical, where the value is in encoded domain knowledge — which signals
matter, which sources to watch, what disqualifies a lead — rather than in the
generality of the builder.

Rilo's investors praised the workflow builder as ahead of the curve. That praise is
also the diagnosis: a builder is infrastructure, and infrastructure gets commoditised
by whoever owns the model.
