"use client";

import { useEffect, useState, useCallback } from "react";
import {
  sourcesApi,
  subscriptionsApi,
  type SourceHealth,
  type Subscription,
} from "@/lib/api";

const SOURCE_META: Record<
  string,
  { label: string; description: string; icon: string }
> = {
  job_boards: {
    label: "Job Boards",
    description:
      "Monitors job postings on LinkedIn, Indeed, and ZipRecruiter for fleet, dispatch, and driver roles that signal company growth and hiring pressure.",
    icon: "📋",
  },
  registry: {
    label: "DOT Registry",
    description:
      "Pulls active carrier records from the FMCSA registry. Surfaces new or recently-updated authority grants and fleet size changes.",
    icon: "📑",
  },
  reddit: {
    label: "Reddit",
    description:
      "Watches r/Truckers, r/logistics, and related subreddits for pain complaints, stack mentions, and decision-maker posts.",
    icon: "💬",
  },
};

function SourceCard({
  source,
  onToggle,
}: {
  source: SourceHealth;
  onToggle: (source: string, enabled: boolean) => void;
}) {
  const meta = SOURCE_META[source.source] ?? {
    label: source.source,
    description: "Collects signal data for this subscription.",
    icon: "🔌",
  };

  const isStale = source.consecutive_empty >= 3;
  const lastRunDate = source.last_run
    ? new Date(source.last_run).toLocaleString()
    : "never";

  return (
    <div
      className={`bg-panel border rounded-sm p-4 space-y-3 ${
        isStale ? "border-amber" : "border-rule"
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden>
            {meta.icon}
          </span>
          <div>
            <p className="text-sm font-mono font-medium text-ink">{meta.label}</p>
            <p className="text-xs font-mono text-ink-soft">{source.source}</p>
          </div>
        </div>
        {/* Toggle */}
        <button
          onClick={() => onToggle(source.source, !source.enabled)}
          className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors focus:outline-none ${
            source.enabled ? "bg-teal" : "bg-rule"
          }`}
          role="switch"
          aria-checked={source.enabled}
          aria-label={`Toggle ${meta.label}`}
        >
          <span
            className={`inline-block h-4 w-4 mt-0.5 rounded-full bg-white shadow transition-transform ${
              source.enabled ? "translate-x-4" : "translate-x-0.5"
            }`}
          />
        </button>
      </div>

      {/* Description */}
      <p className="text-xs font-mono text-ink-soft leading-relaxed">
        {meta.description}
      </p>

      {/* Status row */}
      <div className="border-t border-rule pt-3 flex flex-wrap gap-4">
        <div>
          <p className="text-[10px] font-mono text-ink-soft uppercase tracking-wider">
            Last run
          </p>
          <p className="text-xs font-mono text-ink tabular-nums">{lastRunDate}</p>
        </div>
        <div>
          <p className="text-[10px] font-mono text-ink-soft uppercase tracking-wider">
            Items (last run)
          </p>
          <p className="text-xs font-mono text-ink tabular-nums">
            {source.items_last_run}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-mono text-ink-soft uppercase tracking-wider">
            Consecutive empty
          </p>
          <p
            className={`text-xs font-mono tabular-nums ${
              isStale ? "text-amber font-medium" : "text-ink"
            }`}
          >
            {source.consecutive_empty}
          </p>
        </div>
      </div>

      {/* Warning */}
      {isStale && (
        <div className="bg-amber-wash border border-amber rounded-sm px-3 py-2">
          <p className="text-xs font-mono text-amber">
            Source has returned 0 items for {source.consecutive_empty} consecutive
            runs. Check credentials or signal availability.
          </p>
        </div>
      )}

      {/* Credentials warning */}
      {source.requires_credentials && !source.enabled && (
        <div className="bg-ground border border-rule rounded-sm px-3 py-2">
          <p className="text-xs font-mono text-ink-soft">
            Requires credentials — configure in Settings to enable.
          </p>
        </div>
      )}
    </div>
  );
}

export default function SourcesPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [selectedSub, setSelectedSub] = useState<string>("");
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);

  useEffect(() => {
    subscriptionsApi.list().then((subs) => {
      setSubscriptions(subs);
      if (subs.length > 0) setSelectedSub(subs[0].id);
    });
  }, []);

  const fetchSources = useCallback(async () => {
    if (!selectedSub) return;
    setLoading(true);
    setError(null);
    try {
      const data = await sourcesApi.getHealth(selectedSub);
      setSources(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sources");
    } finally {
      setLoading(false);
    }
  }, [selectedSub]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  async function handleToggle(source: string, enabled: boolean) {
    if (!selectedSub) return;
    setToggling(source);
    try {
      const updated = await sourcesApi.updateSource(selectedSub, source, enabled);
      setSources((prev) =>
        prev.map((s) => (s.source === source ? { ...s, ...updated } : s))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update source");
    } finally {
      setToggling(null);
    }
  }

  const staleCount = sources.filter((s) => s.consecutive_empty >= 3).length;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="font-mono text-lg font-medium text-ink">Sources</h1>
        {staleCount > 0 && (
          <span className="text-xs font-mono text-amber bg-amber-wash px-2 py-0.5 rounded">
            {staleCount} source{staleCount !== 1 ? "s" : ""} need attention
          </span>
        )}
      </div>

      <div className="flex gap-3">
        <select
          value={selectedSub}
          onChange={(e) => setSelectedSub(e.target.value)}
          className="bg-panel border border-rule rounded-sm px-3 py-1.5 text-sm font-mono text-ink focus:outline-none focus:border-teal"
        >
          <option value="">Select subscription</option>
          {subscriptions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="bg-amber-wash border border-rule rounded-sm px-4 py-3">
          <p className="text-sm font-mono text-amber">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="bg-panel border border-rule rounded-sm px-4 py-8 text-center">
          <p className="text-sm font-mono text-ink-soft">loading sources…</p>
        </div>
      ) : sources.length === 0 ? (
        <div className="border-2 border-dashed border-rule rounded-sm px-4 py-12 text-center">
          <p className="text-sm font-mono text-ink-soft">
            {selectedSub ? "no sources configured" : "select a subscription to view sources"}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sources.map((source) => (
            <div
              key={source.source}
              className={toggling === source.source ? "opacity-60 pointer-events-none" : ""}
            >
              <SourceCard source={source} onToggle={handleToggle} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
