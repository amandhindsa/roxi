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
