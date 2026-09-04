"use client"

import { useEffect, useState } from "react"
import { LeadCard } from "./LeadCard"
import type { LeadDetail } from "@/lib/api"

interface Props {
  status: string
  subscriptionId: string
  focusedIndex: number
  onFocusChange: (index: number) => void
}

export function LeadList({ status, subscriptionId, focusedIndex, onFocusChange }: Props) {
  const [leads, setLeads] = useState<LeadDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)

    const params = new URLSearchParams({ status })
    if (subscriptionId) params.set("subscription_id", subscriptionId)

    fetch(`/api/leads?${params}`)
      .then(async r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setLeads(Array.isArray(data) ? data : [])
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [status, subscriptionId])

  const handleDecision = async (
    id: string,
    decision: "approved" | "rejected",
    rejectionReason?: string,
    rejectionNote?: string
  ) => {
    try {
      const body: Record<string, unknown> = { status: decision }
      if (rejectionReason) body.rejection_reason = rejectionReason
      if (rejectionNote) body.rejection_note = rejectionNote

      await fetch(`/api/leads/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      setLeads(prev => prev.filter(l => l.id !== id))
    } catch (err) {
      console.error("decision error", err)
    }
  }

  if (loading) {
    return <p className="text-ink-soft font-mono text-sm py-8">loading…</p>
  }

  if (error) {
    return (
      <div className="border border-dashed border-rule p-8 text-center">
        <p className="text-amber font-mono text-sm">{error}</p>
      </div>
    )
  }

  if (leads.length === 0) {
    return (
      <div className="border border-dashed border-rule p-8 text-center">
        <p className="text-ink-soft font-mono text-sm">No leads in {status}</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {leads.map((lead, i) => (
        <div key={lead.id} onClick={() => onFocusChange(i)}>
          <LeadCard
            lead={lead}
            showActions={status === "pending"}
            focused={focusedIndex === i}
            onDecision={handleDecision}
          />
        </div>
      ))}
    </div>
  )
}
