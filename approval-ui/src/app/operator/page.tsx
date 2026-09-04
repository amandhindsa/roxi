"use client"

import { useEffect, useState, useCallback } from "react"
import {
  operatorApi,
  type OperatorOrg,
  type OperatorSourceHealth,
  type OperatorCosts,
  type OperatorRun,
} from "@/lib/api"

const STORAGE_KEY = "roxi_operator_key"

function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section>
      <h2 className="text-xs font-mono uppercase tracking-wider text-ink-soft mb-3">
        {title}
      </h2>
      {children}
    </section>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="text-left text-[10px] font-mono uppercase tracking-wider text-ink-soft px-3 py-2 font-normal">
      {children}
    </th>
  )
}

function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <td className={`px-3 py-2 text-sm font-mono ${className}`}>{children}</td>
  )
}

export default function OperatorPage() {
  const [key, setKey] = useState("")
  const [keyInput, setKeyInput] = useState("")
  const [keySet, setKeySet] = useState(false)

  const [orgs, setOrgs] = useState<OperatorOrg[]>([])
  const [quietSources, setQuietSources] = useState<OperatorSourceHealth[]>([])
  const [costs, setCosts] = useState<OperatorCosts | null>(null)
  const [runs, setRuns] = useState<OperatorRun[]>([])
  const [loadingOrgs, setLoadingOrgs] = useState(false)
  const [loadingSources, setLoadingSources] = useState(false)
  const [loadingCosts, setLoadingCosts] = useState(false)
  const [loadingRuns, setLoadingRuns] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      setKey(stored)
      setKeySet(true)
    }
  }, [])

  const loadAll = useCallback(async (k: string) => {
    setErrors({})

    setLoadingOrgs(true)
    operatorApi.getOrgs(k)
      .then(setOrgs)
      .catch((e) => setErrors((p) => ({ ...p, orgs: (e as Error).message })))
      .finally(() => setLoadingOrgs(false))

    setLoadingSources(true)
    operatorApi.getSourceHealth(k)
      .then((data) => setQuietSources(data.filter((s) => s.consecutive_empty >= 2)))
      .catch((e) => setErrors((p) => ({ ...p, sources: (e as Error).message })))
      .finally(() => setLoadingSources(false))

    setLoadingCosts(true)
    operatorApi.getCosts(k)
      .then(setCosts)
      .catch((e) => setErrors((p) => ({ ...p, costs: (e as Error).message })))
      .finally(() => setLoadingCosts(false))

    setLoadingRuns(true)
    operatorApi.getRuns(k)
      .then(setRuns)
      .catch((e) => setErrors((p) => ({ ...p, runs: (e as Error).message })))
      .finally(() => setLoadingRuns(false))
  }, [])

  useEffect(() => {
    if (keySet && key) loadAll(key)
  }, [keySet, key, loadAll])

  const handleSetKey = (e: React.FormEvent) => {
    e.preventDefault()
    if (!keyInput.trim()) return
    localStorage.setItem(STORAGE_KEY, keyInput.trim())
    setKey(keyInput.trim())
    setKeySet(true)
    setKeyInput("")
  }

  const handleClearKey = () => {
    localStorage.removeItem(STORAGE_KEY)
    setKey("")
    setKeySet(false)
    setOrgs([])
    setQuietSources([])
    setCosts(null)
    setRuns([])
    setErrors({})
  }

  if (!keySet) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="bg-panel border border-rule p-8 w-full max-w-sm">
          <h1 className="text-lg font-medium mb-1">Operator console</h1>
          <p className="text-ink-soft text-sm font-mono mb-6">
            Enter your operator key to access cross-org data.
          </p>
          <form onSubmit={handleSetKey} className="space-y-3">
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
              placeholder="Operator key…"
              autoFocus
            />
            <button
              type="submit"
              disabled={!keyInput.trim()}
              className="w-full py-2 bg-teal text-white text-sm font-mono hover:opacity-90 disabled:opacity-50"
            >
              Access
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-baseline justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">Operator console</h1>
          <p className="text-ink-soft text-sm font-mono mt-1">
            Cross-org visibility for the Roxi team
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => loadAll(key)}
            className="text-xs font-mono border border-rule px-2.5 py-1 text-ink-soft hover:border-ink hover:text-ink transition-colors"
          >
            refresh
          </button>
          <button
            onClick={handleClearKey}
            className="text-xs font-mono border border-rule px-2.5 py-1 text-ink-soft hover:border-ink hover:text-ink transition-colors"
          >
            clear key
          </button>
        </div>
      </div>

      <div className="space-y-10">
        {/* Orgs */}
        <Section title="All organizations">
          {loadingOrgs ? (
            <p className="text-ink-soft font-mono text-sm">loading…</p>
          ) : errors.orgs ? (
            <p className="text-amber font-mono text-sm">{errors.orgs}</p>
          ) : orgs.length === 0 ? (
            <div className="border border-dashed border-rule py-8 text-center text-ink-soft font-mono text-sm">
              No orgs.
            </div>
          ) : (
            <div className="border border-rule overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-rule bg-ground">
                  <tr>
                    <Th>Name</Th>
                    <Th>Leads</Th>
                    <Th>Cost (USD)</Th>
                    <Th>Last run</Th>
                  </tr>
                </thead>
                <tbody>
                  {orgs.map((org, i) => (
                    <tr key={org.id} className={i < orgs.length - 1 ? "border-b border-rule" : ""}>
                      <Td className="font-medium">{org.name}</Td>
                      <Td>{org.lead_count.toLocaleString()}</Td>
                      <Td>${org.cost_usd.toFixed(4)}</Td>
                      <Td className="text-ink-soft">
                        {org.last_run
                          ? new Date(org.last_run).toLocaleDateString("en-CA")
                          : "never"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* Quiet sources */}
        <Section title="Quiet sources (≥2 consecutive empty)">
          {loadingSources ? (
            <p className="text-ink-soft font-mono text-sm">loading…</p>
          ) : errors.sources ? (
            <p className="text-amber font-mono text-sm">{errors.sources}</p>
          ) : quietSources.length === 0 ? (
            <div className="border border-dashed border-rule py-8 text-center text-ink-soft font-mono text-sm">
              No quiet sources. All good.
            </div>
          ) : (
            <div className="border border-rule overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-rule bg-ground">
                  <tr>
                    <Th>Org</Th>
                    <Th>Source</Th>
                    <Th>Consecutive empty</Th>
                    <Th>Last run</Th>
                  </tr>
                </thead>
                <tbody>
                  {quietSources.map((s, i) => (
                    <tr
                      key={`${s.subscription_id}-${s.source}`}
                      className={`${i < quietSources.length - 1 ? "border-b border-rule" : ""} ${
                        s.consecutive_empty >= 5 ? "bg-amber-wash" : ""
                      }`}
                    >
                      <Td>{s.org_name}</Td>
                      <Td>{s.source}</Td>
                      <Td className={s.consecutive_empty >= 5 ? "text-amber font-medium" : ""}>
                        {s.consecutive_empty}
                      </Td>
                      <Td className="text-ink-soft">
                        {s.last_run
                          ? new Date(s.last_run).toLocaleDateString("en-CA")
                          : "never"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* Daily costs */}
        <Section title="Daily costs (last 14 days)">
          {loadingCosts ? (
            <p className="text-ink-soft font-mono text-sm">loading…</p>
          ) : errors.costs ? (
            <p className="text-amber font-mono text-sm">{errors.costs}</p>
          ) : !costs || costs.daily.length === 0 ? (
            <div className="border border-dashed border-rule py-8 text-center text-ink-soft font-mono text-sm">
              No cost data.
            </div>
          ) : (
            <div className="border border-rule overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-rule bg-ground">
                  <tr>
                    <Th>Date</Th>
                    <Th>Org</Th>
                    <Th>Cost (USD)</Th>
                  </tr>
                </thead>
                <tbody>
                  {costs.daily.slice(-14 * 20).map((row, i) => (
                    <tr key={i} className={i < costs.daily.length - 1 ? "border-b border-rule" : ""}>
                      <Td className="text-ink-soft">{row.date}</Td>
                      <Td>{row.org_name}</Td>
                      <Td>${row.cost_usd.toFixed(4)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* Recent runs */}
        <Section title="Recent runs">
          {loadingRuns ? (
            <p className="text-ink-soft font-mono text-sm">loading…</p>
          ) : errors.runs ? (
            <p className="text-amber font-mono text-sm">{errors.runs}</p>
          ) : runs.length === 0 ? (
            <div className="border border-dashed border-rule py-8 text-center text-ink-soft font-mono text-sm">
              No runs.
            </div>
          ) : (
            <div className="border border-rule overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-rule bg-ground">
                  <tr>
                    <Th>Org</Th>
                    <Th>Subscription</Th>
                    <Th>Started</Th>
                    <Th>Status</Th>
                    <Th>Cost (USD)</Th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run, i) => (
                    <tr key={run.id} className={i < runs.length - 1 ? "border-b border-rule" : ""}>
                      <Td>{run.org_name}</Td>
                      <Td className="text-ink-soft">{run.subscription_id.slice(0, 8)}…</Td>
                      <Td className="text-ink-soft">
                        {new Date(run.started_at).toLocaleString("en-CA", {
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                      </Td>
                      <Td>
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                            run.status === "completed"
                              ? "border-teal text-teal bg-teal-wash"
                              : run.status === "failed"
                              ? "border-amber text-amber bg-amber-wash"
                              : "border-rule text-ink-soft"
                          }`}
                        >
                          {run.status}
                        </span>
                      </Td>
                      <Td>
                        {run.cost_usd != null ? `$${run.cost_usd.toFixed(4)}` : "—"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}
