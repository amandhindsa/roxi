import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const service = process.env.SUPABASE_SERVICE_KEY;

export const supabase = createClient(url, anon);

// Server-side only — bypasses RLS
export const supabaseAdmin = service
  ? createClient(url, service)
  : null;

export type LeadRow = {
  id: string;
  vertical_id: string;
  signal: Signal;
  scored: ScoredSignal;
  research: ResearchBrief | null;
  draft: EmailDraft | null;
  status: "pending" | "approved" | "rejected" | "sent" | "replied";
  created_at: string;
};

export type Signal = {
  company: string;
  company_domain: string | null;
  location: string | null;
  fleet_size: number | null;
  signal_type: "hiring" | "authority_grant" | "pain_complaint";
  signal_date: string | null;
  evidence: string;
  poster_role: "decision_maker" | "driver" | "unknown";
};

export type ScoredSignal = Signal & {
  score: number;
  rules_fired: { rule: string; delta: number }[];
  reasoning: string;
  disqualified_by: string | null;
};

export type ResearchBrief = {
  company_summary: string;
  fleet_estimate: string | null;
  operating_lanes: string[];
  current_stack_guess: string | null;
  decision_maker_title: string | null;
  hooks: string[];
  confidence: "high" | "medium" | "low";
};

export type EmailDraft = {
  why_now: string;
  subject: string;
  body: string;
  hook_used: string;
};
