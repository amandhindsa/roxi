"use client"

import { useEffect, useState } from "react"
import { sourcesApi, type SourceHealth } from "@/lib/api"
import { SubscriptionSelector } from "@/components/SubscriptionSelector"

const SOURCE_LABELS: Record<string, string> = {
  job_boards: "Job Boards",
  registry: "Registry",
  reddit: "Reddit",
}

export default function SourcesPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [sources, setSources] = useState<SourceHealth[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toggling, setToggling] = useState<string | null>(null)

  useEffect(() => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)
    sourcesApi.getHealth(subscriptionId)
      .then(setSources)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [subscriptionId])

  const handleToggle = async (source: SourceHealth) => {
    setToggling(source.source)
    try {
      const updated = await sourcesApi.updateSource(subscriptionId, source.source, !source.enabled)
      setSources(prev => prev.map(s => s.source === source.source ? updated : s))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Toggle failed")
    } finally {
      setToggling(null)
    }
  }

  const formatDate = (iso: string | null) => {
    if (!iso) return "never"
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Sources</h1>
        <SubscriptionSelector value={subscriptionId} onChange={setSubscriptionId} />
      </div>

      {loading && <p className="text-ink-soft font-mono text-sm">loading…</p>}

      {error && (
        <div className="border border-amber bg-amber-wash px-4 py-2 mb-4">
          <p className="text-amber font-mono text-sm">{error}</p>
        </div>
      )}

      {!subscriptionId && !loading && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">Select a subscription to view sources</p>
        </div>
      )}

      {subscriptionId && !loading && sources.length === 0 && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">No sources configured</p>
        </div>
      )}

      {sources.length > 0 && (
        <div className="space-y-3">
          {sources.map(source => (
            <div key={source.source} className="bg-panel border border-rule p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-bold text-base text-ink">
                      {SOURCE_LABELS[source.source] ?? source.source}
                    </span>
                    {source.consecutive_empty >= 3 && (
                      <span className="text-xs font-mono text-amber border border-amber bg-amber-wash px-1.5 py-0.5">
                        quiet · {source.consecutive_empty} empty runs
                      </span>
                    )}
                    {source.requires_credentials && (
                      <span className="text-xs font-mono text-ink-soft border border-rule px-1.5 py-0.5">
                        needs credentials
                      </span>
                    )}
                  </div>
                  <div className="flex gap-4 mt-2 text-xs font-mono text-ink-soft flex-wrap">
                    <span>last run: {formatDate(source.last_run)}</span>
                    <span>items last run: {source.items_last_run}</span>
                    {source.consecutive_empty > 0 && (
                      <span>consecutive empty: {source.consecutive_empty}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`text-xs font-mono ${source.enabled ? "text-teal" : "text-ink-soft"}`}>
                    {source.enabled ? "enabled" : "disabled"}
                  </span>
                  <button
                    onClick={() => handleToggle(source)}
                    disabled={toggling === source.source}
                    className={`relative w-10 h-5 rounded-full transition-colors ${
                      source.enabled ? "bg-teal" : "bg-rule"
                    } disabled:opacity-50`}
                    aria-label={source.enabled ? "Disable source" : "Enable source"}
                  >
                    <span
                      className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                        source.enabled ? "translate-x-5" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
