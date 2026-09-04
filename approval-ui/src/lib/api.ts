// API client for the Roxi backend
// All requests include Authorization: Bearer <token> from the Supabase session

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

async function getToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null
  try {
    const { createBrowserClient } = await import('./supabase')
    const client = createBrowserClient()
    const { data } = await client.auth.getSession()
    return data.session?.access_token ?? null
  } catch {
    return null
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// Leads
export const leadsApi = {
  list(params: { subscription_id?: string; status?: string; vertical?: string; limit?: number; search?: string; date_from?: string; date_to?: string }) {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v != null && q.set(k, String(v)))
    return apiFetch<LeadListItem[]>(`/api/leads?${q}`)
  },
  get(id: string) {
    return apiFetch<LeadDetail>(`/api/leads/${id}`)
  },
  update(id: string, body: { status?: string; rejection_reason?: string; rejection_note?: string; draft_edited_json?: unknown }) {
    return apiFetch<LeadDetail>(`/api/leads/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
  },
  feedback(id: string, body: { outcome: string; note?: string }) {
    return apiFetch<void>(`/api/leads/${id}/feedback`, { method: 'POST', body: JSON.stringify(body) })
  },
}

// Subscriptions
export const subscriptionsApi = {
  list() {
    return apiFetch<Subscription[]>('/api/subscriptions')
  },
  get(id: string) {
    return apiFetch<Subscription>(`/api/subscriptions/${id}`)
  },
  update(id: string, body: Partial<Subscription>) {
    return apiFetch<Subscription>(`/api/subscriptions/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
  },
  create(body: Partial<Subscription>) {
    return apiFetch<Subscription>('/api/subscriptions', { method: 'POST', body: JSON.stringify(body) })
  },
}

// Rules
export const rulesApi = {
  list(subscription_id: string) {
    return apiFetch<RulesVersion[]>(`/api/subscriptions/${subscription_id}/rules`)
  },
  getLatest(subscription_id: string) {
    return apiFetch<RulesVersion>(`/api/subscriptions/${subscription_id}/rules/latest`)
  },
  save(subscription_id: string, rules_text: string) {
    return apiFetch<RulesVersion>(`/api/subscriptions/${subscription_id}/rules`, {
      method: 'POST',
      body: JSON.stringify({ rules_text })
    })
  },
  preview(subscription_id: string, rules_text: string) {
    return apiFetch<RulesPreview>(`/api/subscriptions/${subscription_id}/rules/preview`, {
      method: 'POST',
      body: JSON.stringify({ rules_text })
    })
  },
}

// Setup
export const setupApi = {
  createSession(subscription_id: string) {
    return apiFetch<SetupSession>('/api/setup/sessions', { method: 'POST', body: JSON.stringify({ subscription_id }) })
  },
  getSession(id: string) {
    return apiFetch<SetupSession>(`/api/setup/sessions/${id}`)
  },
  sendMessage(id: string, content: string) {
    return apiFetch<SetupSession>(`/api/setup/sessions/${id}/message`, {
      method: 'POST',
      body: JSON.stringify({ content })
    })
  },
}

// Sources
export const sourcesApi = {
  getHealth(subscription_id: string) {
    return apiFetch<SourceHealth[]>(`/api/subscriptions/${subscription_id}/sources`)
  },
  updateSource(subscription_id: string, source: string, enabled: boolean) {
    return apiFetch<SourceHealth>(`/api/subscriptions/${subscription_id}/sources/${source}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled })
    })
  },
}

// Results
export const resultsApi = {
  getResults(subscription_id: string) {
    return apiFetch<ResultsData>(`/api/subscriptions/${subscription_id}/results`)
  },
}

// Runs
export const runsApi = {
  list(subscription_id?: string) {
    const q = subscription_id ? `?subscription_id=${subscription_id}` : ''
    return apiFetch<Run[]>(`/api/runs${q}`)
  },
  get(id: string) {
    return apiFetch<RunDetail>(`/api/runs/${id}`)
  },
}

// Team / Members
export const teamApi = {
  getMembers(org_id: string) {
    return apiFetch<Member[]>(`/api/orgs/${org_id}/members`)
  },
  inviteMember(org_id: string, email: string, role: string) {
    return apiFetch<Member>(`/api/orgs/${org_id}/members`, {
      method: 'POST',
      body: JSON.stringify({ email, role })
    })
  },
  removeMember(org_id: string, member_id: string) {
    return apiFetch<void>(`/api/orgs/${org_id}/members/${member_id}`, { method: 'DELETE' })
  },
}

// Suppression
export const suppressionApi = {
  list(subscription_id: string) {
    return apiFetch<SuppressionEntry[]>(`/api/subscriptions/${subscription_id}/suppression`)
  },
  add(subscription_id: string, contact: string) {
    return apiFetch<SuppressionEntry>(`/api/subscriptions/${subscription_id}/suppression`, {
      method: 'POST',
      body: JSON.stringify({ contact })
    })
  },
  remove(subscription_id: string, id: string) {
    return apiFetch<void>(`/api/subscriptions/${subscription_id}/suppression/${id}`, { method: 'DELETE' })
  },
}

// Operator (uses a separate key)
export function operatorFetch<T>(path: string, key: string): Promise<T> {
  return fetch(`${API_URL}${path}`, {
    headers: { 'X-Operator-Key': key, 'Content-Type': 'application/json' }
  }).then(r => r.json()) as Promise<T>
}

export const operatorApi = {
  getOrgs: (key: string) => operatorFetch<OperatorOrg[]>('/api/operator/orgs', key),
  getSourceHealth: (key: string) => operatorFetch<OperatorSourceHealth[]>('/api/operator/sources', key),
  getCosts: (key: string) => operatorFetch<OperatorCosts>('/api/operator/costs', key),
  getRuns: (key: string) => operatorFetch<OperatorRun[]>('/api/operator/runs', key),
}

// Types
export type LeadListItem = {
  id: string
  subscription_id: string
  vertical_id: string
  signal: { company: string; location: string | null; signal_type: string; evidence: string; fleet_size: number | null }
  scored: { score: number; rules_fired: { rule: string; delta: number }[]; disqualified_by: string | null }
  status: string
  created_at: string
}

export type LeadDetail = LeadListItem & {
  research: { company_summary: string; fleet_estimate: string | null; operating_lanes: string[]; current_stack_guess: string | null; decision_maker_title: string | null; hooks: string[]; confidence: 'high' | 'medium' | 'low' } | null
  draft: { why_now: string; subject: string; body: string; hook_used: string } | null
  draft_edited_json: { why_now: string; subject: string; body: string; hook_used: string } | null
  rejection_reason: string | null
  rejection_note: string | null
}

export type Subscription = {
  id: string
  org_id: string
  vertical_id: string
  name: string
  status: 'active' | 'paused' | 'cancelled'
  settings: { spend_ceiling_usd: number | null; daily_research_budget: number | null; delivery_hour: number | null; delivery_timezone: string | null; lead_retention_days: number | null }
  sending: { tool: string | null; api_key: string | null; campaign_id: string | null } | null
}

export type RulesVersion = {
  id: string
  version: number
  rules_text: string
  created_at: string
  created_by: string | null
}

export type RulesPreview = {
  qualified_count: number
  previous_count: number
  added: string[]
  removed: string[]
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
  last_run: string | null
  items_last_run: number
  consecutive_empty: number
  enabled: boolean
  requires_credentials: boolean
}

export type ResultsData = {
  by_score_band: { band: string; total: number; replied: number }[]
  rejection_reasons: { reason: string; count: number }[]
}

export type Run = {
  id: string
  subscription_id: string
  started_at: string
  completed_at: string | null
  status: string
  cost_usd: number | null
  summary: { collected: number; extracted: number; deduped: number; qualified: number; researched: number; drafted: number; delivered: number }
}

export type RunDetail = Run & {
  stage_outputs: { stage: string; company: string; drop_reason: string | null; kept: boolean }[]
}

export type Member = {
  id: string
  user_id: string
  email: string
  role: 'owner' | 'reviewer' | 'viewer'
}

export type SuppressionEntry = {
  id: string
  contact: string
  created_at: string
}

export type OperatorOrg = {
  id: string
  name: string
  lead_count: number
  cost_usd: number
  last_run: string | null
}

export type OperatorSourceHealth = {
  subscription_id: string
  org_name: string
  source: string
  consecutive_empty: number
  last_run: string | null
}

export type OperatorCosts = {
  daily: { date: string; org_id: string; org_name: string; cost_usd: number }[]
}

export type OperatorRun = {
  id: string
  org_name: string
  subscription_id: string
  started_at: string
  status: string
  cost_usd: number | null
}
