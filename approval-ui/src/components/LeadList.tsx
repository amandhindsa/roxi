"use client";

import { useEffect, useState } from "react";
import { LeadCard } from "./LeadCard";

type Lead = {
  id: string;
  vertical_id: string;
  signal: {
    company: string;
    location: string | null;
    signal_type: string;
    evidence: string;
    fleet_size: number | null;
  };
  scored: {
    score: number;
    rules_fired: { rule: string; delta: number }[];
    disqualified_by: string | null;
  };
  research: {
    company_summary: string;
    fleet_estimate: string | null;
    operating_lanes: string[];
    current_stack_guess: string | null;
    decision_maker_title: string | null;
    hooks: string[];
    confidence: "high" | "medium" | "low";
  } | null;
  draft: {
    why_now: string;
    subject: string;
    body: string;
    hook_used: string;
  } | null;
  status: string;
  created_at: string;
};

export function LeadList({
  status,
  vertical,
}: {
  status: string;
  vertical: string;
}) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/leads?vertical=${vertical}&status=${status}&limit=50`,
        { cache: "no-store" }
      );
      const data = await res.json();
      setLeads(Array.isArray(data) ? data : []);
    } catch {
      setLeads([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [status, vertical]);

  const handleDecision = async (id: string, decision: "approved" | "rejected") => {
    await fetch(`/api/leads/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: decision }),
    });
    setLeads((prev) => prev.filter((l) => l.id !== id));
  };

  if (loading) {
    return (
      <div className="text-ink-soft font-mono text-sm py-12 text-center">
        Loading…
      </div>
    );
  }

  if (leads.length === 0) {
    return (
      <div className="text-ink-soft font-mono text-sm py-12 text-center border border-dashed border-rule">
        No {status} leads.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-ink-soft font-mono text-xs">
        {leads.length} lead{leads.length !== 1 ? "s" : ""}
      </p>
      {leads.map((lead) => (
        <LeadCard
          key={lead.id}
          lead={lead}
          showActions={status === "pending"}
          onDecision={handleDecision}
        />
      ))}
    </div>
  );
}
