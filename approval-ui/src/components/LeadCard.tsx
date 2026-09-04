"use client"

import { useState } from "react"
import type { LeadDetail } from "@/lib/api"

type RejectionReason = "wrong_size" | "wrong_industry" | "existing_customer" | "bad_timing" | "other"

const REJECTION_LABELS: Record<RejectionReason, string> = {
  wrong_size: "Wrong fleet size",
  wrong_industry: "Wrong industry",
  existing_customer: "Existing customer",
  bad_timing: "Bad timing",
  other: "Other",
}

interface Props {
  lead: LeadDetail
  showActions: boolean
  focused: boolean
  onDecision: (
    id: string,
    decision: "approved" | "rejected",
    rejectionReason?: string,
    rejectionNote?: string
  ) => void
}

export function LeadCard({ lead, showActions, focused, onDecision }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [editingDraft, setEditingDraft] = useState(false)
  const [draftBody, setDraftBody] = useState(
    lead.draft_edited_json?.body ?? lead.draft?.body ?? ""
  )
  const [draftSubject, setDraftSubject] = useState(
    lead.draft_edited_json?.subject ?? lead.draft?.subject ?? ""
  )
  const [savingDraft, setSavingDraft] = useState(false)
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [rejectionReason, setRejectionReason] = useState<RejectionReason>("wrong_size")
  const [rejectionNote, setRejectionNote] = useState("")

  const signal = lead.signal
  const scored = lead.scored
  const research = lead.research
  const draft = lead.draft_edited_json ?? lead.draft

  const scoreColor =
    scored.score >= 80
      ? "text-teal"
      : scored.score >= 60
      ? "text-ink"
      : "text-amber"

  const handleSaveDraft = async () => {
    setSavingDraft(true)
    try {
      await fetch(`/api/leads/${lead.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_edited_json: {
            ...(draft ?? {}),
            subject: draftSubject,
            body: draftBody,
          },
        }),
      })
      setEditingDraft(false)
    } catch (err) {
      console.error(err)
    } finally {
      setSavingDraft(false)
    }
  }

  const handleApprove = () => {
    onDecision(lead.id, "approved")
  }

  const handleRejectConfirm = () => {
    onDecision(lead.id, "rejected", rejectionReason, rejectionNote || undefined)
    setShowRejectForm(false)
  }

  return (
    <div
      className={`bg-panel border border-rule p-4 transition-all ${
        focused ? "ring-2 ring-teal" : ""
      }`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono font-bold text-base text-ink">{signal.company}</span>
            {signal.location && (
              <span className="text-xs font-mono text-ink-soft">{signal.location}</span>
            )}
            {signal.fleet_size && (
              <span className="text-xs font-mono bg-ground border border-rule px-1.5 py-0.5 text-ink-soft">
                {signal.fleet_size} trucks
              </span>
            )}
            <span className="text-xs font-mono bg-ground border border-rule px-1.5 py-0.5 text-ink-soft">
              {signal.signal_type.replace("_", " ")}
            </span>
          </div>
          <p className="text-sm text-ink-soft font-mono mt-1 line-clamp-2">{signal.evidence}</p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`font-mono font-bold text-lg ${scoreColor}`}>{scored.score}</span>
          {scored.disqualified_by && (
            <span className="text-xs font-mono text-amber bg-amber-wash border border-amber px-1.5 py-0.5">
              DQ: {scored.disqualified_by}
            </span>
          )}
        </div>
      </div>

      {/* Rules fired */}
      {scored.rules_fired.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {scored.rules_fired.map((r, i) => (
            <span
              key={i}
              className={`text-xs font-mono px-1.5 py-0.5 border ${
                r.delta > 0
                  ? "text-teal border-teal bg-teal-wash"
                  : "text-amber border-amber bg-amber-wash"
              }`}
            >
              {r.rule} {r.delta > 0 ? "+" : ""}{r.delta}
            </span>
          ))}
        </div>
      )}

      {/* Expand toggle */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="mt-2 text-xs font-mono text-ink-soft hover:text-ink transition-colors"
      >
        {expanded ? "▲ collapse" : "▼ expand"}
      </button>

      {expanded && (
        <div className="mt-4 space-y-4">
          {/* Research */}
          {research && (
            <div className="bg-ground border border-rule p-3">
              <div className="text-xs font-mono text-ink-soft mb-1 uppercase tracking-wide">
                Research · confidence: {research.confidence}
              </div>
              <p className="text-sm font-mono text-ink">{research.company_summary}</p>
              {research.fleet_estimate && (
                <p className="text-xs font-mono text-ink-soft mt-1">Fleet: {research.fleet_estimate}</p>
              )}
              {research.operating_lanes.length > 0 && (
                <p className="text-xs font-mono text-ink-soft mt-1">
                  Lanes: {research.operating_lanes.join(", ")}
                </p>
              )}
              {research.decision_maker_title && (
                <p className="text-xs font-mono text-ink-soft mt-1">
                  DM title: {research.decision_maker_title}
                </p>
              )}
              {research.hooks.length > 0 && (
                <div className="mt-2">
                  <div className="text-xs font-mono text-ink-soft mb-1">Hooks:</div>
                  <ul className="space-y-0.5">
                    {research.hooks.map((h, i) => (
                      <li key={i} className="text-xs font-mono text-ink">· {h}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Draft */}
          {draft && (
            <div className="bg-ground border border-rule p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-mono text-ink-soft uppercase tracking-wide">
                  Email draft {lead.draft_edited_json ? "(edited)" : ""}
                </div>
                {!editingDraft && (
                  <button
                    onClick={() => setEditingDraft(true)}
                    className="text-xs font-mono text-teal hover:opacity-80"
                  >
                    edit
                  </button>
                )}
              </div>

              {editingDraft ? (
                <div className="space-y-2">
                  <div>
                    <label className="text-xs font-mono text-ink-soft block mb-1">Subject</label>
                    <input
                      value={draftSubject}
                      onChange={e => setDraftSubject(e.target.value)}
                      className="w-full border border-rule bg-panel px-2 py-1.5 text-sm font-mono focus:outline-none focus:border-ink"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-mono text-ink-soft block mb-1">Body</label>
                    <textarea
                      value={draftBody}
                      onChange={e => setDraftBody(e.target.value)}
                      rows={8}
                      className="w-full border border-rule bg-panel px-2 py-1.5 text-sm font-mono focus:outline-none focus:border-ink resize-y"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleSaveDraft}
                      disabled={savingDraft}
                      className="text-xs font-mono bg-teal text-white px-3 py-1.5 hover:opacity-90 disabled:opacity-50"
                    >
                      {savingDraft ? "saving…" : "save edit"}
                    </button>
                    <button
                      onClick={() => setEditingDraft(false)}
                      className="text-xs font-mono border border-rule px-3 py-1.5 text-ink-soft hover:text-ink"
                    >
                      cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="text-sm font-mono text-ink font-medium mb-1">
                    {draftSubject}
                  </div>
                  <pre className="text-xs font-mono text-ink whitespace-pre-wrap">{draftBody}</pre>
                  {draft.why_now && (
                    <p className="text-xs font-mono text-ink-soft mt-2 border-t border-rule pt-2">
                      Why now: {draft.why_now}
                    </p>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {showActions && lead.status === "pending" && (
        <div className="mt-4 flex items-center gap-2 flex-wrap">
          {!showRejectForm ? (
            <>
              <button
                onClick={handleApprove}
                className="text-xs font-mono bg-teal text-white px-4 py-2 hover:opacity-90 transition-opacity"
              >
                approve
              </button>
              <button
                onClick={() => setShowRejectForm(true)}
                className="text-xs font-mono border border-rule px-4 py-2 text-ink-soft hover:text-ink transition-colors"
              >
                reject
              </button>
            </>
          ) : (
            <div className="w-full bg-ground border border-rule p-3 space-y-2">
              <div className="text-xs font-mono text-ink-soft mb-1">Rejection reason</div>
              <select
                value={rejectionReason}
                onChange={e => setRejectionReason(e.target.value as RejectionReason)}
                className="w-full border border-rule bg-panel px-2 py-1.5 text-sm font-mono focus:outline-none focus:border-ink"
              >
                {Object.entries(REJECTION_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <input
                type="text"
                value={rejectionNote}
                onChange={e => setRejectionNote(e.target.value)}
                placeholder="Optional note…"
                className="w-full border border-rule bg-panel px-2 py-1.5 text-sm font-mono focus:outline-none focus:border-ink"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleRejectConfirm}
                  className="text-xs font-mono bg-amber-wash border border-amber text-amber px-4 py-1.5 hover:opacity-90"
                >
                  confirm reject
                </button>
                <button
                  onClick={() => setShowRejectForm(false)}
                  className="text-xs font-mono border border-rule px-3 py-1.5 text-ink-soft hover:text-ink"
                >
                  cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Status badge for non-pending */}
      {lead.status !== "pending" && (
        <div className="mt-3 flex items-center gap-2">
          <span
            className={`text-xs font-mono px-2 py-0.5 border ${
              lead.status === "approved" || lead.status === "sent" || lead.status === "replied"
                ? "text-teal border-teal bg-teal-wash"
                : "text-amber border-amber bg-amber-wash"
            }`}
          >
            {lead.status}
          </span>
          {lead.rejection_reason && (
            <span className="text-xs font-mono text-ink-soft">
              {REJECTION_LABELS[lead.rejection_reason as RejectionReason] ?? lead.rejection_reason}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
