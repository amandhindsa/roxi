import { createBrowserClient as _createBrowserClient, createServerClient as _createServerClient } from '@supabase/ssr'
import type { CookieMethodsServer } from '@supabase/ssr'
import { createClient } from '@supabase/supabase-js'
import { cookies } from 'next/headers'

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
const service = process.env.SUPABASE_SERVICE_KEY

// For client components
export function createBrowserClient() {
  return _createBrowserClient(url, anon)
}

// For server components / route handlers
export async function createSupabaseServerClient() {
  const cookieStore = await cookies()
  return _createServerClient(url, anon, {
    cookies: {
      getAll() { return cookieStore.getAll() },
      setAll(cookiesToSet: Parameters<CookieMethodsServer['setAll']>[0]) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        } catch {
          // In Server Components cookies() is read-only — ignore
        }
      }
    }
  })
}

// Legacy exports — kept for backwards compatibility
export const supabase = createClient(url, anon)
export const supabaseAdmin = service ? createClient(url, service) : null

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
