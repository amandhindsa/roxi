"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type HealthCheck = { status: string; checks: Record<string, { status: string; latency_ms?: number; error?: string; vars?: Record<string, string>; http_status?: number }> };
type Stats = { vertical: string; days: number; leads: Record<string, number>; total_leads: number; reply_rate: number | null; llm_cost_usd: number; llm_calls: number };
type Run = { id: string; vertical_id: string; started_at: string; finished_at: string | null; raw_collected: number; signals_extracted: number; signals_qualified: number; leads_delivered: number; total_cost_usd: number };
type CostDay = { day: string; cost_usd: number; calls: number };
type Event = { id: string; event: string; level: string; run_id: string | null; agent: string | null; vertical_id: string | null; data_json: string; created_at: string };

async function get<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${API}${path}`, { cache: "no-store" });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    ok: "bg-teal-wash text-teal",
    degraded: "bg-amber-wash text-amber",
    error: "bg-red-100 text-red-700",
    not_configured: "bg-ground text-ink-soft",
    present: "bg-teal-wash text-teal",
    absent: "bg-ground text-ink-soft",
    MISSING: "bg-red-100 text-red-700",
  };
  const cls = map[status] ?? "bg-ground text-ink-soft";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono font-medium ${cls}`}>
      {status}
    </span>
  );
}

function MetricCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-panel border border-rule rounded-sm p-4">
      <p className="text-xs font-mono text-ink-soft uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-mono font-medium tabular-nums text-ink">{value}</p>
      {sub && <p className="text-xs font-mono text-ink-soft mt-1">{sub}</p>}
    </div>
  );
}

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 0.001);
  const w = 120, h = 32, pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - (v / max) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const area = `M${pts.join("L")}L${w - pad},${h - pad}L${pad},${h - pad}Z`;
  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={area} fill="#D8EDEB" />
      <polyline points={pts.join(" ")} fill="none" stroke="#106B5E" strokeWidth="1.5" />
      {/* last point dot */}
      <circle cx={pts[pts.length - 1].split(",")[0]} cy={pts[pts.length - 1].split(",")[1]} r="2" fill="#106B5E" />
    </svg>
  );
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [costs, setCosts] = useState<CostDay[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [h, s, r, c, e] = await Promise.all([
      get<HealthCheck>("/health"),
      get<Stats>("/api/stats"),
      get<Run[]>("/api/runs?limit=10"),
      get<CostDay[]>("/api/telemetry/costs?days=14"),
      get<Event[]>("/api/telemetry/events?limit=30"),
    ]);
    if (h) setHealth(h);
    if (s) setStats(s);
    if (r) setRuns(r);
    if (c) setCosts(c);
    if (e) setEvents(e);
    setLastRefresh(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, [refresh]);

  const overallOk = health?.status === "ok";
  const costSeries = costs.map(d => d.cost_usd);

  return (
    <div className="space-y-8">
      {/* Header row */}
      <div className="flex items-baseline justify-between">
        <h1 className="font-mono text-lg font-medium text-ink">Control Dashboard</h1>
        <div className="flex items-center gap-3">
          <span className={`w-2 h-2 rounded-full inline-block ${overallOk ? "bg-teal" : "bg-amber"}`} />
          <span className="text-xs font-mono text-ink-soft">
            {lastRefresh ? `refreshed ${lastRefresh.toLocaleTimeString()}` : "loading…"}
          </span>
          <button onClick={refresh} className="text-xs font-mono text-ink-soft hover:text-ink underline underline-offset-2">
            refresh
          </button>
        </div>
      </div>

      {/* Health checks */}
      <section>
        <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">Health</h2>
        <div className="bg-panel border border-rule rounded-sm divide-y divide-rule">
          {health ? Object.entries(health.checks).map(([name, check]) => (
            <div key={name} className="flex items-center justify-between px-4 py-2.5">
              <span className="font-mono text-sm text-ink">{name}</span>
              <div className="flex items-center gap-3">
                {check.latency_ms != null && (
                  <span className="text-xs font-mono text-ink-soft tabular-nums">{check.latency_ms}ms</span>
                )}
                {check.error && (
                  <span className="text-xs font-mono text-red-600 max-w-xs truncate">{check.error}</span>
                )}
                <StatusPill status={check.status} />
              </div>
            </div>
          )) : (
            <div className="px-4 py-3 text-sm font-mono text-ink-soft">
              {loading ? "connecting…" : "API unreachable — is the server running?"}
            </div>
          )}
          {health?.checks?.env?.vars && (
            <div className="px-4 py-3">
              <p className="text-xs font-mono text-ink-soft mb-2 uppercase tracking-wider">Environment vars</p>
              <div className="grid grid-cols-2 gap-1">
                {Object.entries(health.checks.env.vars).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-2">
                    <span className="text-xs font-mono text-ink-soft truncate">{k}</span>
                    <StatusPill status={v} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Funnel metrics */}
      {stats && (
        <section>
          <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">
            Funnel — {stats.vertical} (last {stats.days}d)
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="Total leads" value={stats.total_leads} />
            <MetricCard
              label="Reply rate"
              value={stats.reply_rate != null ? `${(stats.reply_rate * 100).toFixed(1)}%` : "—"}
              sub={stats.reply_rate != null && stats.reply_rate < 0.08 && stats.total_leads >= 10 ? "⚠ below 8% threshold" : undefined}
            />
            <MetricCard
              label="LLM cost"
              value={`$${stats.llm_cost_usd.toFixed(3)}`}
              sub={`${stats.llm_calls} calls`}
            />
            <MetricCard
              label="Cost / lead"
              value={stats.total_leads > 0
                ? `$${(stats.llm_cost_usd / stats.total_leads).toFixed(3)}`
                : "—"}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 md:grid-cols-6 gap-2">
            {Object.entries(stats.leads).map(([status, n]) => (
              <div key={status} className="bg-panel border border-rule rounded-sm px-3 py-2">
                <p className="text-xs font-mono text-ink-soft">{status}</p>
                <p className="text-lg font-mono font-medium tabular-nums">{n}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Cost sparkline */}
      {costs.length > 1 && (
        <section>
          <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">Daily cost (14d)</h2>
          <div className="bg-panel border border-rule rounded-sm px-4 py-4 flex items-end gap-4">
            <Sparkline data={costSeries} />
            <div className="text-xs font-mono text-ink-soft space-y-1">
              <p>peak <span className="text-ink tabular-nums">${Math.max(...costSeries).toFixed(3)}</span></p>
              <p>avg <span className="text-ink tabular-nums">${(costSeries.reduce((a, b) => a + b, 0) / costSeries.length).toFixed(3)}</span></p>
            </div>
          </div>
        </section>
      )}

      {/* Run history */}
      <section>
        <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">Pipeline runs</h2>
        <div className="bg-panel border border-rule rounded-sm overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-rule text-ink-soft">
                {["vertical", "started", "collected", "extracted", "qualified", "delivered", "cost"].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-medium uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {runs.length === 0 ? (
                <tr><td colSpan={7} className="px-3 py-4 text-ink-soft">{loading ? "loading…" : "no runs yet"}</td></tr>
              ) : runs.map(r => (
                <tr key={r.id} className="hover:bg-ground transition-colors">
                  <td className="px-3 py-2 text-ink">{r.vertical_id}</td>
                  <td className="px-3 py-2 text-ink-soft tabular-nums">{new Date(r.started_at).toLocaleString()}</td>
                  <td className="px-3 py-2 tabular-nums">{r.raw_collected}</td>
                  <td className="px-3 py-2 tabular-nums">{r.signals_extracted}</td>
                  <td className="px-3 py-2 tabular-nums">{r.signals_qualified}</td>
                  <td className="px-3 py-2 font-medium tabular-nums">{r.leads_delivered}</td>
                  <td className="px-3 py-2 tabular-nums text-ink-soft">${r.total_cost_usd.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Event log */}
      <section>
        <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">Event log</h2>
        <div className="bg-panel border border-rule rounded-sm overflow-x-auto max-h-64 overflow-y-auto">
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-panel border-b border-rule">
              <tr className="text-ink-soft">
                {["time", "event", "level", "agent", "vertical", "data"].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-medium uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {events.length === 0 ? (
                <tr><td colSpan={6} className="px-3 py-4 text-ink-soft">{loading ? "loading…" : "no events"}</td></tr>
              ) : events.map(e => {
                const data = (() => { try { return JSON.parse(e.data_json); } catch { return {}; } })();
                const levelCls = e.level === "error" ? "text-red-600" : e.level === "warning" ? "text-amber" : "text-ink-soft";
                return (
                  <tr key={e.id} className="hover:bg-ground transition-colors">
                    <td className="px-3 py-1.5 text-ink-soft tabular-nums whitespace-nowrap">
                      {new Date(e.created_at).toLocaleTimeString()}
                    </td>
                    <td className="px-3 py-1.5 text-ink">{e.event}</td>
                    <td className={`px-3 py-1.5 ${levelCls}`}>{e.level}</td>
                    <td className="px-3 py-1.5 text-ink-soft">{e.agent ?? "—"}</td>
                    <td className="px-3 py-1.5 text-ink-soft">{e.vertical_id ?? "—"}</td>
                    <td className="px-3 py-1.5 text-ink-soft max-w-xs truncate">
                      {Object.entries(data).map(([k, v]) => `${k}=${String(v)}`).join(" ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
