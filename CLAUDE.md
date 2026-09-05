# Roxi — Project Intelligence

Roxi is a multi-tenant GTM pipeline that finds companies showing buying signals,
researches them, drafts outreach emails, and queues them for human approval before
sending via Instantly. It is **not** a fire-and-forget bot — every message requires
explicit human approval.

---

## Architecture

```
Job Boards / Reddit / Registry
        ↓
   Collectors  →  Extractor  →  Dedupe  →  Scorer  →  Researcher  →  Drafter
                                                                          ↓
                                                              Approval UI (Next.js)
                                                                          ↓
                                                                    Instantly API
```

- **Backend:** FastAPI + Uvicorn (`roxi/api/app.py`) — deployed on Railway
- **Frontend:** Next.js 15 approval UI (`approval-ui/`) — deployed on Vercel
- **Database:** Supabase (production) / SQLite (`roxi.db`, dev only)
- **Scheduler:** APScheduler BackgroundScheduler, started in FastAPI lifespan
- **Multi-tenancy unit:** `subscription` — one org can have multiple subscriptions

---

## Infrastructure

### Railway (backend)
- **Public URL:** `https://roxi-production.up.railway.app`
- **Internal:** `roxi.railway.internal`
- **Project:** `trustworthy-nurturing` (`647698c5-4007-42e8-8477-0bba00c8b655`)
- **Service:** `roxi` (`95d33bc4-fa6d-456e-b6be-8d3374a7b840`)
- **Environment:** `production` (`860a166a-1bed-4229-8341-079c4bb36e19`)
- **Workspace:** `959f4cbc-14ab-40de-90ed-3a6ef85d2721`
- **Deploy trigger:** git push to `main` → auto-deploy via GitHub integration
- **GraphQL API:** `https://backboard.railway.app/graphql/v2`

### Vercel (frontend)
- **Team:** `transportgold` (`team_iIwphhkMAvA7L5ph2riDx5US`)
- **Project:** `roxi` (`prj_EWfAYGX5heqkiT1H7KjJaVEzdsqd`)
- **Production domain:** `roxi-git-main-transportgold.vercel.app`
- **Deploy trigger:** git push to `main` → auto-deploy via GitHub integration
- **Root directory:** `approval-ui/`

### Supabase
- **Project ref:** `tiqqmwcevfomkcazefbc`
- **URL:** `https://tiqqmwcevfomkcazefbc.supabase.co`
- **Dashboard:** `https://supabase.com/dashboard/project/tiqqmwcevfomkcazefbc`

### GitHub
- **Repo:** `amandhindsa/roxi` (public)

---

## Credentials

All credentials are in `/Users/bigbear/Desktop/Roxi/.env.local`.
Load them with: `source .env.local` or read the file directly.

| Variable | Purpose |
|---|---|
| `VERCEL_TOKEN` | Vercel API — full account scope, team `transportgold` |
| `RAILWAY_TOKEN` | Railway GraphQL API — user token |
| `RAILWAY_PROJECT_TOKEN` | Railway CLI token (project-scoped, not for API) |
| `SUPABASE_SERVICE_KEY` | Supabase service role — bypasses RLS, full access |
| `SUPABASE_JWT_SECRET` | Legacy HS256 JWT secret — backend uses this to verify UI tokens |
| `OPERATOR_API_KEY` | X-Operator-Key header for the internal operator console |

**Railway env vars set on the service:**
`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET`, `USE_SUPABASE=1`,
`ANTHROPIC_API_KEY`, `ROXI_API_KEY`, `OPERATOR_API_KEY`

**Vercel env vars needed:**
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `ROXI_API_URL`,
`NEXT_PUBLIC_SHOW_OPERATOR`

---

## How to Deploy

Both Railway and Vercel auto-deploy on `git push origin main`. That's it.

To check deploy status after a push, use `/roxi-status`.
To watch logs, use `/roxi-logs`.

---

## How to Run Locally

```bash
# Backend
pip install -e ".[supabase]"
USE_SUPABASE=1 python -m roxi serve   # or: uvicorn roxi.api.app:app --port 8080

# Frontend
cd approval-ui
npm install
npm run dev   # http://localhost:3000
```

---

## Key Files

| Path | What it does |
|---|---|
| `roxi/api/app.py` | FastAPI app — all 40+ endpoints, JWT auth, lifespan |
| `roxi/pipeline.py` | Main pipeline orchestrator |
| `roxi/store.py` | SQLite store (delegates to Supabase when USE_SUPABASE=1) |
| `roxi/store_supabase.py` | Supabase store — 67 functions |
| `roxi/scheduler.py` | APScheduler — daily runs per subscription |
| `roxi/agents/interviewer.py` | Conversational onboarding interview |
| `roxi/models.py` | All Pydantic models |
| `roxi/config.py` | VerticalConfig loader |
| `verticals/hauler_ai.yaml` | Vertical config for hauler_ai |
| `approval-ui/src/app/` | Next.js pages |
| `approval-ui/src/lib/api.ts` | Typed API client (all endpoints) |
| `approval-ui/src/lib/supabase.ts` | Supabase browser client + all domain types |
| `scripts/setup_supabase.sql` | Full schema + RLS — idempotent, safe to re-run |

---

## Security Constraints (non-negotiable)

- **Nothing sends itself.** Every lead requires explicit approval in the UI.
- **Reddit is read-only.** Auto-posting violates Reddit ToS.
- **LinkedIn automation is banned.** Violates their user agreement.
- **CASL compliance.** Express or implied consent required before any outreach.
- **Approval is per-message, not a mode.** No "auto-approve" mode.

---

## Multi-Tenancy Model

- `organisation` → has many `members` (owner/reviewer/viewer roles)
- `subscription` → belongs to org, targets one vertical, has its own rules version
- All leads, runs, and dedupe keys are scoped to `subscription_id`
- RLS enforced via `current_org_id()` Supabase function
- Operator console (`/operator`) uses `X-Operator-Key` header, not user JWT

---

## Available Skills

- `/roxi-status` — check Railway + Vercel deploy state and recent logs
- `/roxi-logs` — tail Railway logs
- `/roxi-deploy` — push, watch both deploys, screenshot the result
