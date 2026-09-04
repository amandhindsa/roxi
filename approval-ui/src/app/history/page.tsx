"use client"

import { useState } from "react"
import { LeadCard } from "@/components/LeadCard"
import { SubscriptionSelector } from "@/components/SubscriptionSelector"
import type { LeadDetail } from "@/lib/api"

const STATUS_OPTIONS = ["", "pending", "approved", "rejected", "sent", "replied"]

export default function HistoryPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [filterStatus, setFilterStatus] = useState("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [search, setSearch] = useState("")
  const [leads, setLeads] = useState<LeadDetail[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const handleSearch = async () => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)
    setSearched(true)

    const params = new URLSearchParams()
    params.set("subscription_id", subscriptionId)
    if (filterStatus) params.set("status", filterStatus)
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    if (search) params.set("search", search)

    try {
      const res = await fetch(`/api/leads?${params}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setLeads(Array.isArray(data) ? data : [])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })

  return (
    <div>
      <h1 className="font-mono font-bold text-lg text-ink mb-6">Lead history</h1>

      {/* Filters */}
      <div className="bg-panel border border-rule p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-mono text-ink-soft">Subscription</label>
          <SubscriptionSelector value={subscriptionId} onChange={setSubscriptionId} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-mono text-ink-soft">Status</label>
          <select
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)}
            className="border border-rule bg-ground px-3 py-1.5 text-sm font-mono text-ink focus:outline-none"
          >
            {STATUS_OPTIONS.map(s => (
              <option key={s} value={s}>{s || "all"}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-mono text-ink-soft">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={e => setDateFrom(e.target.value)}
            className="border border-rule bg-ground px-3 py-1.5 text-sm font-mono text-ink focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-mono text-ink-soft">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={e => setDateTo(e.target.value)}
            className="border border-rule bg-ground px-3 py-1.5 text-sm font-mono text-ink focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1 flex-1 min-w-[160px]">
          <label className="text-xs font-mono text-ink-soft">Company search</label>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Company name…"
            className="border border-rule bg-ground px-3 py-1.5 text-sm font-mono text-ink focus:outline-none"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={!subscriptionId || loading}
          className="px-4 py-1.5 bg-teal text-white text-sm font-mono hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {loading ? "searching…" : "search"}
        </button>
      </div>

      {/* Results */}
      {error && (
        <div className="border border-dashed border-amber p-6 text-center">
          <p className="text-amber font-mono text-sm">{error}</p>
        </div>
      )}

      {!searched && !loading && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">Set filters and click search</p>
        </div>
      )}

      {searched && !loading && !error && leads.length === 0 && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">No leads match these filters</p>
        </div>
      )}

      {leads.length > 0 && (
        <div>
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="border-b border-rule text-left">
                <th className="py-2 pr-4 text-xs text-ink-soft font-medium">company</th>
                <th className="py-2 pr-4 text-xs text-ink-soft font-medium">score</th>
                <th className="py-2 pr-4 text-xs text-ink-soft font-medium">status</th>
                <th className="py-2 pr-4 text-xs text-ink-soft font-medium">signal</th>
                <th className="py-2 text-xs text-ink-soft font-medium">date</th>
              </tr>
            </thead>
            <tbody>
              {leads.map(lead => (
                <>
                  <tr
                    key={lead.id}
                    onClick={() => setExpandedId(expandedId === lead.id ? null : lead.id)}
                    className="border-b border-rule cursor-pointer hover:bg-panel transition-colors"
                  >
                    <td className="py-2 pr-4 text-ink font-medium">{lead.signal.company}</td>
                    <td className="py-2 pr-4">
                      <span
                        className={`${
                          lead.scored.score >= 80
                            ? "text-teal"
                            : lead.scored.score >= 60
                            ? "text-ink"
                            : "text-amber"
                        } font-bold`}
                      >
                        {lead.scored.score}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className={`text-xs px-1.5 py-0.5 border ${
                          ["approved", "sent", "replied"].includes(lead.status)
                            ? "text-teal border-teal bg-teal-wash"
                            : lead.status === "rejected"
                            ? "text-amber border-amber bg-amber-wash"
                            : "text-ink-soft border-rule bg-ground"
                        }`}
                      >
                        {lead.status}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-ink-soft text-xs">{lead.signal.signal_type.replace("_", " ")}</td>
                    <td className="py-2 text-ink-soft text-xs">{formatDate(lead.created_at)}</td>
                  </tr>
                  {expandedId === lead.id && (
                    <tr key={`${lead.id}-expanded`}>
                      <td colSpan={5} className="pb-4 pt-1">
                        <LeadCard
                          lead={lead}
                          showActions={false}
                          focused={false}
                          onDecision={() => {}}
                        />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
