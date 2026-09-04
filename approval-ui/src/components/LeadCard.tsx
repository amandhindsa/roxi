"use client";

import { useState } from "react";

type Lead = {
  id: string;
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

const SIGNAL_LABELS: Record<string, string> = {
  hiring: "hiring",
  authority_grant: "authority",
  pain_complaint: "pain",
};

const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-teal-wash text-teal",
  medium: "bg-amber-wash text-amber",
  low: "bg-gray-100 text-ink-soft",
};

export function LeadCard({
  lead,
  showActions,
  onDecision,
}: {
  lead: Lead;
  showActions: boolean;
  onDecision: (id: string, decision: "approved" | "rejected") => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [acting, setActing] = useState(false);

  const { signal, scored, research, draft } = lead;
  const date = new Date(lead.created_at).toLocaleDateString("en-CA");

  const handleDecision = async (decision: "approved" | "rejected") => {
    setActing(true);
    await onDecision(lead.id, decision);
    setActing(false);
  };

  const scoreColor =
    scored.score >= 80
      ? "text-teal"
      : scored.score >= 70
      ? "text-ink"
      : "text-ink-soft";

  return (
    <div className="bg-panel border border-rule">
      {/* Header row */}
      <div className="px-5 py-4 flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="font-medium text-base">{signal.company}</span>
            {signal.location && (
              <span className="text-ink-soft text-sm font-mono">{signal.location}</span>
            )}
            <span className="text-xs font-mono border border-rule px-1.5 py-0.5 text-ink-soft">
              {SIGNAL_LABELS[signal.signal_type] || signal.signal_type}
            </span>
            {signal.fleet_size && (
              <span className="text-xs font-mono text-ink-soft">{signal.fleet_size} units</span>
            )}
          </div>
          {draft?.why_now && (
            <p className="text-sm text-ink mt-1.5 leading-snug">{draft.why_now}</p>
          )}
          <p className="text-xs text-ink-soft font-mono mt-1.5 italic">
            "{signal.evidence}"
          </p>
        </div>

        <div className="flex flex-col items-end gap-2 shrink-0">
          <span className={`font-mono font-medium text-lg leading-none ${scoreColor}`}>
            {scored.score}
          </span>
          <span className="text-ink-soft font-mono text-[10px]">/100</span>
        </div>
      </div>

      {/* Rules fired */}
      <div className="px-5 pb-3 flex flex-wrap gap-1.5">
        {scored.rules_fired.map((r, i) => (
          <span
            key={i}
            className="text-[11px] font-mono bg-ground border border-rule px-1.5 py-0.5 text-ink-soft"
          >
            +{r.delta} {r.rule.length > 40 ? r.rule.slice(0, 38) + "…" : r.rule}
          </span>
        ))}
      </div>

      {/* Expand toggle */}
      <button
        className="w-full px-5 py-2 border-t border-rule text-left text-xs font-mono text-ink-soft hover:text-ink flex items-center gap-2 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <span>{expanded ? "▲" : "▼"}</span>
        {expanded ? "hide" : "show draft + research"}
      </button>

      {expanded && (
        <div className="border-t border-rule">
          {/* Draft email */}
          {draft && (
            <div className="px-5 py-4 border-b border-rule">
              <p className="text-xs font-mono text-ink-soft uppercase tracking-wider mb-2">
                Draft email
              </p>
              <p className="text-sm font-medium mb-1">Subject: {draft.subject}</p>
              <pre className="text-sm whitespace-pre-wrap font-sans text-ink leading-relaxed bg-ground p-3 border border-rule">
                {draft.body}
              </pre>
              <p className="text-xs font-mono text-ink-soft mt-2">
                Hook: {draft.hook_used}
              </p>
            </div>
          )}

          {/* Research brief */}
          {research && (
            <div className="px-5 py-4">
              <div className="flex items-center gap-2 mb-3">
                <p className="text-xs font-mono text-ink-soft uppercase tracking-wider">
                  Research
                </p>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 ${
                    CONFIDENCE_STYLES[research.confidence]
                  }`}
                >
                  {research.confidence} confidence
                </span>
              </div>
              <p className="text-sm text-ink mb-3">{research.company_summary}</p>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm mb-3">
                {research.fleet_estimate && (
                  <>
                    <span className="text-ink-soft font-mono text-xs">Fleet</span>
                    <span>{research.fleet_estimate}</span>
                  </>
                )}
                {research.operating_lanes.length > 0 && (
                  <>
                    <span className="text-ink-soft font-mono text-xs">Lanes</span>
                    <span>{research.operating_lanes.join(", ")}</span>
                  </>
                )}
                {research.current_stack_guess && (
                  <>
                    <span className="text-ink-soft font-mono text-xs">Stack</span>
                    <span>{research.current_stack_guess}</span>
                  </>
                )}
                {research.decision_maker_title && (
                  <>
                    <span className="text-ink-soft font-mono text-xs">DM title</span>
                    <span>{research.decision_maker_title}</span>
                  </>
                )}
              </div>
              {research.hooks.length > 0 && (
                <ul className="text-sm space-y-1">
                  {research.hooks.map((h, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-teal mt-0.5">•</span>
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {showActions && (
        <div className="px-5 py-3 border-t border-rule flex gap-3">
          <button
            disabled={acting}
            onClick={() => handleDecision("approved")}
            className="flex-1 py-2 text-sm font-mono font-medium bg-teal text-white hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            Approve
          </button>
          <button
            disabled={acting}
            onClick={() => handleDecision("rejected")}
            className="flex-1 py-2 text-sm font-mono border border-rule text-ink-soft hover:text-ink hover:border-ink transition-colors disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}

      {/* Footer */}
      <div className="px-5 py-2 border-t border-rule flex justify-between text-[10px] font-mono text-ink-soft">
        <span>{lead.id.slice(0, 8)}</span>
        <span>{date}</span>
      </div>
    </div>
  );
}
