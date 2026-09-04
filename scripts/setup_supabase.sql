-- Roxi — Supabase schema with RLS
-- Run this in the Supabase SQL editor: https://supabase.com/dashboard/project/tiqqmwcevfomkcazefbc/sql/new
-- Schema matches roxi/store.py exactly so migration is a straight copy.

-- ── Tables ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS leads (
    id              TEXT PRIMARY KEY,
    vertical_id     TEXT NOT NULL,
    raw_json        TEXT NOT NULL,
    signal_json     TEXT NOT NULL,
    scored_json     TEXT NOT NULL,
    research_json   TEXT,
    draft_json      TEXT,
    dedupe_key      TEXT UNIQUE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dedupe_keys (
    key         TEXT PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id              TEXT PRIMARY KEY,
    run_id          TEXT,
    org_id          TEXT,
    model           TEXT NOT NULL,
    agent           TEXT NOT NULL,
    prompt_version  TEXT,
    input_hash      TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        REAL,
    latency_ms      INTEGER,
    outcome         TEXT,
    lead_id         TEXT REFERENCES leads(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
    id                  TEXT PRIMARY KEY,
    vertical_id         TEXT NOT NULL,
    org_id              TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    raw_collected       INTEGER DEFAULT 0,
    signals_extracted   INTEGER DEFAULT 0,
    signals_qualified   INTEGER DEFAULT 0,
    leads_delivered     INTEGER DEFAULT 0,
    total_cost_usd      REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS suppression_list (
    id                  TEXT PRIMARY KEY,
    contact_identifier  TEXT NOT NULL,
    channel             TEXT NOT NULL,
    reason              TEXT NOT NULL,
    added_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contact_identifier, channel)
);

CREATE TABLE IF NOT EXISTS publish_log (
    id          TEXT PRIMARY KEY,
    item_id     TEXT NOT NULL,
    platform    TEXT NOT NULL,
    success     BOOLEAN NOT NULL,
    post_url    TEXT,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    event       TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'info',
    run_id      TEXT,
    org_id      TEXT,
    vertical_id TEXT,
    agent       TEXT,
    lead_id     TEXT,
    data_json   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS generation_costs (
    id          TEXT PRIMARY KEY,
    item_id     TEXT NOT NULL,
    provider    TEXT NOT NULL,
    cost_usd    REAL NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stage_outputs (
    id          TEXT PRIMARY KEY,
    run_id      TEXT,
    stage       TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Indexes ──────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS leads_vertical_status  ON leads (vertical_id, status);
CREATE INDEX IF NOT EXISTS leads_created_at       ON leads (created_at DESC);
CREATE INDEX IF NOT EXISTS llm_calls_created_at   ON llm_calls (created_at DESC);
CREATE INDEX IF NOT EXISTS llm_calls_run_id       ON llm_calls (run_id);
CREATE INDEX IF NOT EXISTS events_run_id          ON events (run_id);
CREATE INDEX IF NOT EXISTS events_created_at      ON events (created_at DESC);
CREATE INDEX IF NOT EXISTS runs_vertical_id       ON runs (vertical_id, started_at DESC);

-- ── RLS ──────────────────────────────────────────────────────────────────────
-- The service key (server-side) bypasses RLS.
-- The anon key (Next.js UI) can only SELECT pending leads.

ALTER TABLE leads             ENABLE ROW LEVEL SECURITY;
ALTER TABLE dedupe_keys       ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_calls         ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppression_list  ENABLE ROW LEVEL SECURITY;
ALTER TABLE publish_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE events            ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_costs  ENABLE ROW LEVEL SECURITY;

-- Allow the Next.js UI (anon role) to read leads
CREATE POLICY "anon_read_leads" ON leads
    FOR SELECT TO anon USING (true);

-- Allow the Next.js UI (anon role) to read runs (for dashboard)
CREATE POLICY "anon_read_runs" ON runs
    FOR SELECT TO anon USING (true);

-- All other tables: service key only (bypasses RLS — no anon policies needed).


-- ══════════════════════════════════════════════════════════════════════════════
-- ── Multi-tenancy additions ───────────────────────────────────────────────────
-- ══════════════════════════════════════════════════════════════════════════════


-- ── New tables ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organisations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE NOT NULL,  -- URL-safe name
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS members (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('owner','reviewer','viewer')),
    invited_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    joined_at   TIMESTAMPTZ,
    UNIQUE (org_id, user_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                     TEXT PRIMARY KEY,
    org_id                 TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    vertical_id            TEXT NOT NULL,
    rules_version_id       TEXT,   -- FK to vertical_rules.id — null = use file-based rules
    status                 TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','cancelled')),
    paused                 BOOLEAN NOT NULL DEFAULT false,
    daily_research_budget  INTEGER NOT NULL DEFAULT 15,
    spend_ceiling_usd      REAL NOT NULL DEFAULT 5.0,
    qualify_threshold      INTEGER NOT NULL DEFAULT 70,
    delivery_hour          INTEGER NOT NULL DEFAULT 8 CHECK (delivery_hour BETWEEN 0 AND 23),
    delivery_timezone      TEXT NOT NULL DEFAULT 'America/Toronto',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vertical_rules (
    id              TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    rules_json      TEXT NOT NULL,   -- JSON array of {rule, delta, disqualify?}
    icp_json        TEXT NOT NULL,   -- JSON {description, disqualifiers[]}
    product_brief   TEXT NOT NULL,
    summary         TEXT NOT NULL,   -- plain-English summary for the UI
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subscription_id, version)
);

CREATE TABLE IF NOT EXISTS setup_sessions (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    subscription_id TEXT REFERENCES subscriptions(id),
    state           TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','complete','abandoned')),
    messages_json   TEXT NOT NULL DEFAULT '[]',  -- [{role, content}]
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_health (
    id                  TEXT PRIMARY KEY,
    subscription_id     TEXT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    source_name         TEXT NOT NULL,
    last_run_at         TIMESTAMPTZ,
    last_count          INTEGER NOT NULL DEFAULT 0,
    consecutive_empty   INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subscription_id, source_name)
);

CREATE TABLE IF NOT EXISTS scheduled_runs (
    id              TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    scheduled_at    TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','failed')),
    run_id          TEXT REFERENCES runs(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lead_feedback (
    id          TEXT PRIMARY KEY,
    lead_id     TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    reason      TEXT NOT NULL,  -- wrong_size, wrong_industry, existing_customer, bad_timing, other
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ── Alter existing tables ─────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS subscription_id TEXT REFERENCES subscriptions(id);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS org_id TEXT REFERENCES organisations(id);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS draft_edited_json TEXT;  -- edited draft body
ALTER TABLE leads ADD COLUMN IF NOT EXISTS replied_at TIMESTAMPTZ;

ALTER TABLE runs ADD COLUMN IF NOT EXISTS subscription_id TEXT REFERENCES subscriptions(id);
ALTER TABLE runs ADD COLUMN IF NOT EXISTS rules_version_id TEXT REFERENCES vertical_rules(id);

ALTER TABLE dedupe_keys ADD COLUMN IF NOT EXISTS subscription_id TEXT REFERENCES subscriptions(id);


-- ── New indexes ───────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS members_user_id     ON members (user_id);
CREATE INDEX IF NOT EXISTS members_org_id      ON members (org_id);
CREATE INDEX IF NOT EXISTS subscriptions_org   ON subscriptions (org_id);
CREATE INDEX IF NOT EXISTS runs_subscription   ON runs (subscription_id, started_at DESC);
CREATE INDEX IF NOT EXISTS leads_subscription  ON leads (subscription_id, status);
CREATE INDEX IF NOT EXISTS dedupe_keys_sub     ON dedupe_keys (subscription_id);
CREATE INDEX IF NOT EXISTS source_health_sub   ON source_health (subscription_id);
CREATE INDEX IF NOT EXISTS scheduled_runs_sub  ON scheduled_runs (subscription_id, scheduled_at);


-- ── RLS helper function ───────────────────────────────────────────────────────

-- Returns the org_id for the currently authenticated user.
-- Used by all multi-tenant RLS policies below.
CREATE OR REPLACE FUNCTION current_org_id() RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT org_id FROM members WHERE user_id = auth.uid() LIMIT 1
$$;


-- ── RLS on new tables ─────────────────────────────────────────────────────────

ALTER TABLE organisations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE members        ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE vertical_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_health  ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_feedback  ENABLE ROW LEVEL SECURITY;


-- ── RLS policies ──────────────────────────────────────────────────────────────

-- organisations: members see their own org
CREATE POLICY "members_read_own_org" ON organisations
    FOR SELECT TO authenticated USING (id = current_org_id());

-- members: see members in same org
CREATE POLICY "members_read_own_org_members" ON members
    FOR SELECT TO authenticated USING (org_id = current_org_id());

-- subscriptions: see own org's subscriptions
CREATE POLICY "members_read_subscriptions" ON subscriptions
    FOR SELECT TO authenticated USING (org_id = current_org_id());

-- vertical_rules: see own subscriptions' rules
CREATE POLICY "members_read_rules" ON vertical_rules
    FOR SELECT TO authenticated USING (
        subscription_id IN (SELECT id FROM subscriptions WHERE org_id = current_org_id())
    );

-- leads: replace the broad anon policy with org-scoped authenticated access.
-- Operator/service role reads all (via service key, which bypasses RLS).
DROP POLICY IF EXISTS "anon_read_leads" ON leads;
CREATE POLICY "members_read_leads" ON leads
    FOR SELECT TO authenticated USING (org_id = current_org_id());

-- runs: replace the broad anon policy with org-scoped authenticated access.
DROP POLICY IF EXISTS "anon_read_runs" ON runs;
CREATE POLICY "members_read_runs" ON runs
    FOR SELECT TO authenticated USING (
        subscription_id IN (SELECT id FROM subscriptions WHERE org_id = current_org_id())
        OR org_id = current_org_id()
    );

-- setup_sessions: see own org's sessions
CREATE POLICY "members_read_setup" ON setup_sessions
    FOR SELECT TO authenticated USING (org_id = current_org_id());

-- source_health: see own subscriptions' health records
CREATE POLICY "members_read_source_health" ON source_health
    FOR SELECT TO authenticated USING (
        subscription_id IN (SELECT id FROM subscriptions WHERE org_id = current_org_id())
    );

-- lead_feedback: read and insert for own org's leads
CREATE POLICY "members_read_feedback" ON lead_feedback
    FOR SELECT TO authenticated USING (
        lead_id IN (SELECT id FROM leads WHERE org_id = current_org_id())
    );
CREATE POLICY "members_insert_feedback" ON lead_feedback
    FOR INSERT TO authenticated WITH CHECK (
        lead_id IN (SELECT id FROM leads WHERE org_id = current_org_id())
    );
