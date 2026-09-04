"use client"

import { useEffect, useState, useCallback } from "react"
import { LeadList } from "@/components/LeadList"
import { SubscriptionSelector } from "@/components/SubscriptionSelector"

const STATUS_TABS = ["pending", "approved", "rejected", "sent", "replied"] as const
type Status = typeof STATUS_TABS[number]

export default function LeadsPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [status, setStatus] = useState<Status>("pending")
  const [focusedIndex, setFocusedIndex] = useState(0)

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return

    if (e.key === "j") setFocusedIndex(i => i + 1)
    if (e.key === "k") setFocusedIndex(i => Math.max(0, i - 1))
    if (e.key === "a") {
      // approve focused — dispatched via a custom event
      window.dispatchEvent(new CustomEvent("roxi:approve", { detail: { index: focusedIndex } }))
    }
    if (e.key === "r") {
      window.dispatchEvent(new CustomEvent("roxi:reject", { detail: { index: focusedIndex } }))
    }
    if (e.key === "e") {
      window.dispatchEvent(new CustomEvent("roxi:expand", { detail: { index: focusedIndex } }))
    }
  }, [focusedIndex])

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [handleKeyDown])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Lead queue</h1>
        <SubscriptionSelector value={subscriptionId} onChange={setSubscriptionId} />
      </div>

      {/* Status tabs */}
      <div className="flex gap-0 border-b border-rule mb-6">
        {STATUS_TABS.map(tab => (
          <button
            key={tab}
            onClick={() => { setStatus(tab); setFocusedIndex(0) }}
            className={`px-4 py-2 text-xs font-mono border-b-2 transition-colors ${
              status === tab
                ? "border-teal text-teal font-bold"
                : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {subscriptionId ? (
        <LeadList
          status={status}
          subscriptionId={subscriptionId}
          focusedIndex={focusedIndex}
          onFocusChange={setFocusedIndex}
        />
      ) : (
        <div className="border border-dashed border-rule p-8 text-center">
          <p className="text-ink-soft font-mono text-sm">Select a subscription to view leads</p>
        </div>
      )}

      {/* Keyboard hint */}
      <div className="mt-8 pt-4 border-t border-rule">
        <p className="text-xs font-mono text-ink-soft text-center">
          a approve · r reject · j/k navigate · e expand
        </p>
      </div>
    </div>
  )
}
