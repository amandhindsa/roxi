"use client"

import { useEffect, useState } from "react"
import { runsApi, type Run, type RunDetail } from "@/lib/api"
import { SubscriptionSelector } from "@/components/SubscriptionSelector"

export default function RunsPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [expandedRun, setExpandedRun] = useState<RunDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  useEffect(() => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)
    runsApi.list(subscriptionId)
      .then(setRuns)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [subscriptionId])

  const handleExpandRun = async (runId: string) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null)
      setExpandedRun(null)
      return
    }
    setExpandedRunId(runId)
    setLoadingDetail(true)
    try {
      const detail = await runsApi.get(runId)
      setExpandedRun(detail)
    } catch {
      setExpandedRun(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    })

  const statusColor = (s: string) => {
    if (s === "complete") return "text-teal border-teal bg-teal-wash"
    if (s === "failed") return "text-amber border-amber bg-amber-wash"
    return "text-ink-soft border-rule bg-ground"
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Run history</h1>
        <SubscriptionSelector value={subscriptionId} onChange={setSubscriptionId} />
      </div>

      {loading && <p className="text-ink-soft font-mono text-sm">loading…</p>}

      {error && (
        <div className="border border-dashed border-amber p-8 text-center">
          <p className="text-amber font-mono text-sm">{error}</p>
        </div>
      )}

      {!loading && !error && !subscriptionId && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">Select a subscription to view runs</p>
        </div>
      )}

      {!loading && !error && subscriptionId && runs.length === 0 && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">No runs found</p>
        </div>
      )}

      {runs.length > 0 && (
        <div className="space-y-2">
          {runs.map(run => (
            <div key={run.id} className="bg-panel border border-rule">
              <div
                className="p-4 cursor-pointer hover:bg-ground transition-colors"
                onClick={() => handleExpandRun(run.id)}
              >
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <div className="flex items-center gap-3">
                    <span className={`text-xs font-mono px-1.5 py-0.5 border ${statusColor(run.status)}`}>
                      {run.status}
                    </span>
                    <span className="text-sm font-mono text-ink">{formatDate(run.started_at)}</span>
                    {run.cost_usd != null && (
                      <span className="text-xs font-mono text-ink-soft">${run.cost_usd.toFixed(3)}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs font-mono text-ink-soft flex-wrap">
                    {run.summary && (
                      <>
                        <span>{run.summary.collected} collected</span>
                        <span className="text-rule">→</span>
                        <span>{run.summary.extracted} extracted</span>
                        <span className="text-rule">→</span>
                        <span>{run.summary.deduped} deduped</span>
                        <span className="text-rule">→</span>
                        <span className="text-teal">{run.summary.qualified} qualified</span>
                        <span className="text-rule">→</span>
                        <span>{run.summary.researched} researched</span>
                        <span className="text-rule">→</span>
                        <span>{run.summary.drafted} drafted</span>
                        <span className="text-rule">→</span>
                        <span className="text-teal font-bold">{run.summary.delivered} delivered</span>
                      </>
                    )}
                  </div>
                  <span className="text-xs font-mono text-ink-soft">
                    {expandedRunId === run.id ? "▲" : "▼"}
                  </span>
                </div>
              </div>

              {expandedRunId === run.id && (
                <div className="border-t border-rule p-4">
                  {loadingDetail && (
                    <p className="text-ink-soft font-mono text-sm">loading detail…</p>
                  )}
                  {expandedRun && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs font-mono">
                        <thead>
                          <tr className="border-b border-rule text-left">
                            <th className="py-1.5 pr-4 text-ink-soft font-medium">stage</th>
                            <th className="py-1.5 pr-4 text-ink-soft font-medium">company</th>
                            <th className="py-1.5 pr-4 text-ink-soft font-medium">kept</th>
                            <th className="py-1.5 text-ink-soft font-medium">drop reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {expandedRun.stage_outputs.map((row, i) => (
                            <tr key={i} className="border-b border-rule">
                              <td className="py-1 pr-4 text-ink-soft">{row.stage}</td>
                              <td className="py-1 pr-4 text-ink">{row.company}</td>
                              <td className="py-1 pr-4">
                                {row.kept ? (
                                  <span className="text-teal">✓</span>
                                ) : (
                                  <span className="text-amber">✗</span>
                                )}
                              </td>
                              <td className="py-1 text-ink-soft">{row.drop_reason ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
