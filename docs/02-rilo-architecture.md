# Rilo — architecture

Rilo never published an engineering blog or architecture documentation. What follows
separates what their materials state from what can be reasonably inferred.

---

## 1. Confirmed from Rilo's own materials

**MCP-based tooling.** Their documentation described an MCP system connecting agents
to dozens of operations. They also shipped a separate "Growth MCP" product. Tool
connectivity ran through MCP rather than bespoke per-integration glue.

**100+ integrations**, in two visible classes:

- API connectors — Gmail, Slack, Notion, HubSpot, Salesforce, Apollo, Instantly, Zapier
- Scrapers — Reddit, Twitter, Facebook (asset names: `RedditScraperTool`,
  `TwitterScraperTool`, `FacebookScraperTool`)

The split matters. Where an API existed they used it; where it did not, they scraped.

**A natural-language-to-workflow compiler.** Their careers page: *"You just describe
what you want to automate and the system builds the workflow for you. No templates. No
dragging blocks."* The builder asked clarifying questions, then produced a workflow
that "knows what done looks like."

**A managed reliability layer** — their stated differentiator, and the most
architecturally revealing claim they made. The platform "interprets your intent, sets
up the integrations, manages tokens, adds guardrails, and self corrects when something
goes off." They framed the problem explicitly: workflows fail quietly, data gets stuck
between apps, OAuth dies.

**Server-side inference.** An FAQ entry confirmed users did not need to bring their own
API keys.

**Scheduled execution with human approval.** Daily digests delivered to Slack or email;
drafts queued for review; an FAQ entry addressing whether anything sends without
approval.

---

## 2. Not disclosed

- Which foundation models, or whether model-agnostic
- Orchestration framework
- Memory or state architecture
- Language and infrastructure stack
- How the compiled workflow was represented

---

## 3. Inferred design — reasoning, not fact

### Where the model sat

The strongest inference from the product surface is that **the expensive reasoning
happened at build time, not run time**.

Evidence: the builder asks clarifying questions and constructs the workflow live in
minutes; setup is advertised at three minutes; runs then execute daily on a schedule
against a fixed outcome definition.

That pattern only makes sense if ambiguity is resolved once, with a human present, and
compiled into a durable artifact. If the model re-planned on every daily run, identical
inputs would produce drifting behaviour and per-run cost would scale badly across
10,000 users on a free tier.

**Inferred shape:** natural language → clarifying dialogue → structured workflow spec
(a DAG of typed steps) → persisted → executed deterministically, with LLM calls only at
steps requiring judgment (relevance ranking, drafting).

### What "self-corrects" probably means

Not an autonomous agent re-planning. More likely: per-step retry with error context fed
back, schema validation on step outputs, and a fallback path that escalates a failed
deterministic step to a model call. Combined with token refresh handling, this covers
the failure modes they named.

### Cost architecture

A free first workflow with 10,000 users demands aggressive tiering. Almost certainly:
cheap models for extraction and filtering, expensive models only for synthesis and
drafting, with hard caps per workflow run.

---

## 4. Architectural lessons for Roxi

| Rilo choice | Take it? | Reasoning |
|---|---|---|
| MCP tool layer | **Yes** | Standardised tool connectivity, avoids per-integration glue |
| Compile intent once, execute deterministically | **Yes** | The single most important design decision |
| API-first with scraper fallback | **Yes** | Correct handling of platforms without usable APIs |
| Managed OAuth and token refresh | **Yes, but buy it** | Real value, zero differentiation, months of work |
| Human approval gate by default | **Yes** | Non-negotiable for outbound |
| Server-side inference, no BYO keys | **Yes** | Better UX; requires strict cost tiering |
| Free first workflow | **No** | Fuelled 10k users and immaterial revenue |
| Fully general workflow builder | **No** | This is the strategic error — see below |
| 100+ integrations at 6 people | **No** | Breadth over depth; each connector is a maintenance tax |

### The one to reject deliberately

The general builder was Rilo's headline feature and, in hindsight, its ceiling. It put
them in direct competition with Claude Cowork and ChatGPT Work — products with more
distribution, better models, and no need to maintain 100 connectors.

Roxi should invert this: a narrow, opinionated system where the moat is encoded domain
knowledge for a specific vertical. Not "describe any workflow," but "we already know
what a buying signal looks like for Canadian carriers, and you don't."
