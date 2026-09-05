"use client"

import { createBrowserClient as _createBrowserClient } from '@supabase/ssr'
import { createClient } from '@supabase/supabase-js'

// For client components
export function createBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  return _createBrowserClient(url, anon)
}

// Legacy lazy singletons — safe to use client-side only
let _supabase: ReturnType<typeof createClient> | null = null
let _supabaseAdmin: ReturnType<typeof createClient> | null = null

export function getSupabase() {
  if (!_supabase) {
    _supabase = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    )
  }
  return _supabase
}

export function getSupabaseAdmin() {
  const service = process.env.SUPABASE_SERVICE_KEY
  if (!_supabaseAdmin && service) {
    _supabaseAdmin = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, service)
  }
  return _supabaseAdmin
}

// Keep legacy named exports for backwards compat — but make them lazy proxies
// that won't blow up at module load time when env vars aren't set
export const supabase = new Proxy({} as ReturnType<typeof createClient>, {
  get(_target, prop) {
    return (getSupabase() as unknown as Record<string | symbol, unknown>)[prop]
  }
})
export const supabaseAdmin = new Proxy({} as ReturnType<typeof createClient>, {
  get(_target, prop) {
    const admin = getSupabaseAdmin()
    if (!admin) return undefined
    return (admin as unknown as Record<string | symbol, unknown>)[prop]
  }
})

// Types
export type LeadRow = {
  id: string
  vertical_id: string
  subscription_id: string
  signal: Signal
  scored: ScoredSignal
  research: ResearchBrief | null
  draft: EmailDraft | null
  draft_edited_json: EmailDraft | null
  status: 'pending' | 'approved' | 'rejected' | 'sent' | 'replied'
  rejection_reason: RejectionReason | null
  rejection_note: string | null
  created_at: string
}

export type Signal = {
  company: string
  company_domain: string | null
  location: string | null
  fleet_size: number | null
  signal_type: 'hiring' | 'authority_grant' | 'pain_complaint'
  signal_date: string | null
  evidence: string
  poster_role: 'decision_maker' | 'driver' | 'unknown'
}

export type ScoredSignal = Signal & {
  score: number
  rules_fired: { rule: string; delta: number }[]
  reasoning: string
  disqualified_by: string | null
}

export type ResearchBrief = {
  company_summary: string
  fleet_estimate: string | null
  operating_lanes: string[]
  current_stack_guess: string | null
  decision_maker_title: string | null
  hooks: string[]
  confidence: 'high' | 'medium' | 'low'
}

export type EmailDraft = {
  why_now: string
  subject: string
  body: string
  hook_used: string
}

export type RejectionReason = 'wrong_size' | 'wrong_industry' | 'existing_customer' | 'bad_timing' | 'other'

export type Org = {
  id: string
  name: string
  slug: string
  created_at: string
}

export type Member = {
  id: string
  org_id: string
  user_id: string
  email: string
  role: 'owner' | 'reviewer' | 'viewer'
  created_at: string
}

export type Subscription = {
  id: string
  org_id: string
  vertical_id: string
  name: string
  status: 'active' | 'paused' | 'cancelled'
  settings: {
    spend_ceiling_usd: number | null
    daily_research_budget: number | null
    delivery_hour: number | null
    delivery_timezone: string | null
  }
  created_at: string
}

export type VerticalRules = {
  id: string
  subscription_id: string
  version: number
  rules_text: string
  created_at: string
  created_by: string | null
}

export type SetupSession = {
  id: string
  subscription_id: string
  state: 'active' | 'complete'
  messages: { role: 'user' | 'assistant'; content: string; created_at: string }[]
  summary: string | null
  created_at: string
}

export type SourceHealth = {
  source: string
  subscription_id: string
  last_run: string | null
  items_last_run: number
  consecutive_empty: number
  enabled: boolean
  requires_credentials: boolean
}
