"use client"

import { useEffect, useState } from "react"
import { operatorApi, type OperatorOrg, type OperatorSourceHealth, type OperatorCosts, type OperatorRun } from "@/lib/api"

const KEY_STORAGE = "roxi_operator_key"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-panel border border-rule p-4 mb-6">
      <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-3">{title}</div>
      {children}
    </div>
  )
}

export default function OperatorPage() {
  const [key, setKey] = useState<string | null>(null)
  const [keyInput, setKeyInput] = useState("")
  const [keySubmitting, setKeySubmitting] = useState(false)

  const [orgs, setOrgs] = useState<OperatorOrg[]>([])
  const [quietSources, setQuietSources] = useState<OperatorSourceHealth[]>([])
  const [costs, setCosts] = useState<OperatorCosts | null>(null)
  const [runs, setRuns] = useState<OperatorRun[]>([])

  const [loadingOrgs, setLoadingOrgs] = useState(false)
  const [loadingSources, setLoadingSources] = useState(false)
  const [loadingCosts, setLoadingCosts] = useState(false)
  const [loadingRuns, setLoadingRuns] = useState(false)

  const [errorOrgs, setErrorOrgs] = useState<string | null>(null)
  const [errorSources, setErrorSources] = useState<string | null>(null)
  const [errorCosts, setErrorCosts] = useState<string | null>(null)
  const [errorRuns, setErrorRuns] = useState<string | null>(null)

  useEffect(() => {
    const saved = localStorage.getItem(KEY_STORAGE)
    if (saved) setKey(saved)
  }, [])

  useEffect(() => {
    if (!key) return
    loadAll(key)
  }, [key])

  const loadAll = (k: string) => {
    setLoadingOrgs(true)
    setErrorOrgs(null)
    operatorApi.getOrgs(k)
      .then(setOrgs)
      .catch(err => setErrorOrgs(err.message))
      .finally(() => setLoadingOrgs(false))

    setLoadingSources(true)
    setErrorSources(null)
    operatorApi.getSourceHealth(k)
      .then(data => setQuietSources(data.filter(s => s.consecutive_empty >= 2)))
      .catch(err => setErrorSources(err.message))
      .finally(() => setLoadingSources(false))

    setLoadingCosts(true)
    setErrorCosts(null)
    operatorApi.getCosts(k)
      .then(setCosts)
      .catch(err => setErrorCosts(err.message))
      .finally(() => setLoadingCosts(false))

    setLoadingRuns(true)
    setErrorRuns(null)
    operatorApi.getRuns(k)
      .then(setRuns)
      .catch(err => setErrorRuns(err.message))
      .finally(() => setLoadingRuns(false))
  }

  const handleKeySubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!keyInput.trim()) return
    setKeySubmitting(true)
    localStorage.setItem(KEY_STORAGE, keyInput.trim())
    setKey(keyInput.trim())
    setKeySubmitting(false)
  }

  const handleClearKey = () => {
    localStorage.removeItem(KEY_STORAGE)
    setKey(null)
    setKeyInput("")
    setOrgs([])
    setQuietSources([])
    setCosts(null)
    setRuns([])
  }

  const formatDate = (iso: string | null) => {
    if (!iso) return "never"
    return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" })
  }

  const formatDateTime = (iso: string) =>
    new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    })

  if (!key) {
    return (
      <div>
        <h1 className="font-mono font-bold text-lg text-ink mb-6">Operator console</h1>
        <div className="bg-panel border border-rule p-8 max-w-sm">
          <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-4">
            Enter operator key
          </div>
          <form onSubmit={handleKeySubmit} className="space-y-3">
            <input
              type="password"
              value={keyInput}
              onChange={e => setKeyInput(e.target.value)}
              placeholder="op_..."
              required
              className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
            />
            <button
              type="submit"
              disabled={keySubmitting || !keyInput.trim()}
              className="w-full py-2 bg-teal text-white text-sm font-mono hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {keySubmitting ? "entering…" : "enter"}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Operator console</h1>
        <button
          onClick={handleClearKey}
          className="text-xs font-mono text-ink-soft hover:text-ink border border-rule px-3 py-1.5"
        >
          clear key
        </button>
      </div>

      {/* Orgs */}
      <Section title="All organisations">
        {loadingOrgs && <p className="text-ink-soft font-mono text-sm">loading…</p>}
        {errorOrgs && <p className="text-amber font-mono text-sm">{errorOrgs}</p>}
        {!loadingOrgs && !errorOrgs && orgs.length === 0 && (
          <p className="text-ink-soft font-mono text-sm">No organisations</p>
        )}
        {orgs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="border-b border-rule text-left">
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">name</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">leads</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">cost</th>
                  <th className="py-1.5 text-xs text-ink-soft font-medium">last run</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map(org => (
                  <tr key={org.id} className="border-b border-rule last:border-0">
                    <td className="py-1.5 pr-4 text-ink">{org.name}</td>
                    <td className="py-1.5 pr-4 text-ink-soft">{org.lead_count}</td>
                    <td className="py-1.5 pr-4 text-ink-soft">${org.cost_usd.toFixed(2)}</td>
                    <td className="py-1.5 text-ink-soft">{formatDate(org.last_run)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Quiet sources */}
      <Section title="Quiet sources (≥2 empty runs)">
        {loadingSources && <p className="text-ink-soft font-mono text-sm">loading…</p>}
        {errorSources && <p className="text-amber font-mono text-sm">{errorSources}</p>}
        {!loadingSources && !errorSources && quietSources.length === 0 && (
          <div className="border border-dashed border-rule p-6 text-center">
            <p className="text-ink-soft font-mono text-sm">No quiet sources</p>
          </div>
        )}
        {quietSources.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="border-b border-rule text-left">
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">org</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">source</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">consecutive empty</th>
                  <th className="py-1.5 text-xs text-ink-soft font-medium">last run</th>
                </tr>
              </thead>
              <tbody>
                {quietSources.map((s, i) => (
                  <tr key={i} className="border-b border-rule last:border-0">
                    <td className="py-1.5 pr-4 text-ink">{s.org_name}</td>
                    <td className="py-1.5 pr-4 text-ink">{s.source}</td>
                    <td className="py-1.5 pr-4">
                      <span className={`text-xs px-1.5 py-0.5 border ${
                        s.consecutive_empty >= 5
                          ? "text-amber border-amber bg-amber-wash"
                          : "text-ink-soft border-rule bg-ground"
                      }`}>
                        {s.consecutive_empty}
                      </span>
                    </td>
                    <td className="py-1.5 text-ink-soft">{formatDate(s.last_run)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Daily costs */}
      <Section title="Daily costs (last 14 days)">
        {loadingCosts && <p className="text-ink-soft font-mono text-sm">loading…</p>}
        {errorCosts && <p className="text-amber font-mono text-sm">{errorCosts}</p>}
        {!loadingCosts && !errorCosts && (!costs || costs.daily.length === 0) && (
          <div className="border border-dashed border-rule p-6 text-center">
            <p className="text-ink-soft font-mono text-sm">No cost data</p>
          </div>
        )}
        {costs && costs.daily.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="border-b border-rule text-left">
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">date</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">org</th>
                  <th className="py-1.5 text-xs text-ink-soft font-medium">cost (USD)</th>
                </tr>
              </thead>
              <tbody>
                {costs.daily.map((row, i) => (
                  <tr key={i} className="border-b border-rule last:border-0">
                    <td className="py-1.5 pr-4 text-ink-soft">{row.date}</td>
                    <td className="py-1.5 pr-4 text-ink">{row.org_name}</td>
                    <td className="py-1.5 text-ink">${row.cost_usd.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Recent runs */}
      <Section title="Recent runs">
        {loadingRuns && <p className="text-ink-soft font-mono text-sm">loading…</p>}
        {errorRuns && <p className="text-amber font-mono text-sm">{errorRuns}</p>}
        {!loadingRuns && !errorRuns && runs.length === 0 && (
          <div className="border border-dashed border-rule p-6 text-center">
            <p className="text-ink-soft font-mono text-sm">No runs</p>
          </div>
        )}
        {runs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="border-b border-rule text-left">
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">org</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">subscription</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">started</th>
                  <th className="py-1.5 pr-4 text-xs text-ink-soft font-medium">status</th>
                  <th className="py-1.5 text-xs text-ink-soft font-medium">cost</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run.id} className="border-b border-rule last:border-0">
                    <td className="py-1.5 pr-4 text-ink">{run.org_name}</td>
                    <td className="py-1.5 pr-4 text-ink-soft font-mono text-xs">
                      {run.subscription_id.slice(0, 8)}…
                    </td>
                    <td className="py-1.5 pr-4 text-ink-soft text-xs">{formatDateTime(run.started_at)}</td>
                    <td className="py-1.5 pr-4">
                      <span className={`text-xs px-1.5 py-0.5 border ${
                        run.status === "complete"
                          ? "text-teal border-teal bg-teal-wash"
                          : run.status === "failed"
                          ? "text-amber border-amber bg-amber-wash"
                          : "text-ink-soft border-rule bg-ground"
                      }`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="py-1.5 text-ink-soft text-xs">
                      {run.cost_usd != null ? `$${run.cost_usd.toFixed(3)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  )
}
