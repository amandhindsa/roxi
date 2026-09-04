"use client";

import { useEffect, useState, useCallback } from "react";
import {
  resultsApi,
  subscriptionsApi,
  type ResultsData,
  type Subscription,
} from "@/lib/api";

const SCORE_BANDS = ["0–50", "50–60", "60–70", "70–80", "80–90", "90+"];

function ScoreBandChart({
  data,
}: {
  data: { band: string; total: number; replied: number }[];
}) {
  const maxTotal = Math.max(...data.map((d) => d.total), 1);
  const band90plus = data.find((d) => d.band === "90+" || d.band === "90-100");
  const band70plus = data.filter(
    (d) =>
      d.band === "70–80" ||
      d.band === "70-80" ||
      d.band === "80–90" ||
      d.band === "80-90" ||
      d.band === "90+" ||
      d.band === "90-100"
  );
  const band70Total = band70plus.reduce((a, b) => a + b.total, 0);
  const band70Replied = band70plus.reduce((a, b) => a + b.replied, 0);
  const band90Rate =
    band90plus && band90plus.total > 0
      ? band90plus.replied / band90plus.total
      : null;
  const band70Rate =
    band70Total > 0 ? band70Replied / band70Total : null;
  const showInsight =
    band90Rate !== null &&
    band70Rate !== null &&
    band90Rate - band70Rate < 0.05 &&
    band90plus!.total >= 5;

  const BAR_MAX_HEIGHT = 120;

  return (
    <div className="space-y-4">
      {showInsight && (
        <div className="bg-amber-wash border border-amber rounded-sm px-4 py-3">
          <p className="text-sm font-mono text-amber font-medium">
            Score calibration warning
          </p>
          <p className="text-xs font-mono text-amber mt-1">
            The 90+ band replies at {(band90Rate! * 100).toFixed(1)}% vs{" "}
            {(band70Rate! * 100).toFixed(1)}% for the 70+ band — a difference of{" "}
            {((band90Rate! - band70Rate!) * 100).toFixed(1)}pp. Your scoring rules may
            not be differentiating top leads. Consider tightening the 90+ criteria.
          </p>
        </div>
      )}

      <div className="bg-panel border border-rule rounded-sm p-4">
        <p className="text-xs font-mono text-ink-soft uppercase tracking-wider mb-6">
          Reply rate by score band
        </p>
        <div className="flex items-end gap-4">
          {data.map((band) => {
            const barH = Math.max(4, (band.total / maxTotal) * BAR_MAX_HEIGHT);
            const repliedH =
              band.total > 0
                ? (band.replied / band.total) * barH
                : 0;
            const rate =
              band.total > 0
                ? ((band.replied / band.total) * 100).toFixed(0)
                : "—";

            return (
              <div key={band.band} className="flex flex-col items-center gap-2 flex-1">
                {/* Bar */}
                <div
                  className="relative w-full rounded-sm bg-ground overflow-hidden"
                  style={{ height: `${BAR_MAX_HEIGHT}px` }}
                  title={`${band.total} total, ${band.replied} replied (${rate}%)`}
                >
                  {/* Total bar */}
                  <div
                    className="absolute bottom-0 left-0 right-0 bg-teal-wash rounded-sm"
                    style={{ height: `${barH}px` }}
                  />
                  {/* Replied overlay */}
                  <div
                    className="absolute bottom-0 left-0 right-0 bg-teal rounded-sm"
                    style={{ height: `${repliedH}px` }}
                  />
                </div>
                {/* Labels */}
                <div className="text-center">
                  <p className="text-xs font-mono font-medium text-ink tabular-nums">
                    {rate}%
                  </p>
                  <p className="text-[10px] font-mono text-ink-soft tabular-nums">
                    {band.replied}/{band.total}
                  </p>
                  <p className="text-[10px] font-mono text-ink-soft mt-0.5">
                    {band.band}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-4 flex items-center gap-4 border-t border-rule pt-3">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-teal" />
            <span className="text-xs font-mono text-ink-soft">replied</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm bg-teal-wash" />
            <span className="text-xs font-mono text-ink-soft">total</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function RejectionChart({
  data,
  totalApproved,
  totalRejected,
}: {
  data: { reason: string; count: number }[];
  totalApproved: number;
  totalRejected: number;
}) {
  const maxCount = Math.max(...data.map((d) => d.count), 1);
  const totalDecided = totalApproved + totalRejected;
  const approvalRate =
    totalDecided > 0 ? ((totalApproved / totalDecided) * 100).toFixed(1) : "—";

  return (
    <div className="bg-panel border border-rule rounded-sm p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <p className="text-xs font-mono text-ink-soft uppercase tracking-wider">
          Rejection reasons
        </p>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-ink-soft">
            approval rate
          </span>
          <span className="text-sm font-mono font-medium text-ink tabular-nums">
            {approvalRate}%
          </span>
          <span className="text-xs font-mono text-ink-soft tabular-nums">
            ({totalApproved}/{totalDecided})
          </span>
        </div>
      </div>

      {data.length === 0 ? (
        <div className="border-2 border-dashed border-rule rounded-sm px-4 py-8 text-center">
          <p className="text-sm font-mono text-ink-soft">no rejections recorded</p>
        </div>
      ) : (
        <div className="space-y-2">
          {[...data]
            .sort((a, b) => b.count - a.count)
            .map((item) => {
              const pct = (item.count / maxCount) * 100;
              const sharePct =
                totalRejected > 0
                  ? ((item.count / totalRejected) * 100).toFixed(0)
                  : "0";
              return (
                <div key={item.reason} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-ink">
                      {item.reason.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs font-mono text-ink-soft tabular-nums">
                      {item.count} ({sharePct}%)
                    </span>
                  </div>
                  <div className="h-2 bg-ground rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

export default function ResultsPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [selectedSub, setSelectedSub] = useState<string>("");
  const [results, setResults] = useState<ResultsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    subscriptionsApi.list().then((subs) => {
      setSubscriptions(subs);
      if (subs.length > 0) setSelectedSub(subs[0].id);
    });
  }, []);

  const fetchResults = useCallback(async () => {
    if (!selectedSub) return;
    setLoading(true);
    setError(null);
    try {
      const data = await resultsApi.getResults(selectedSub);
      setResults(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load results");
    } finally {
      setLoading(false);
    }
  }, [selectedSub]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const totalApproved =
    results?.by_score_band.reduce((a, b) => a + b.replied, 0) ?? 0;
  const totalRejected =
    results?.rejection_reasons.reduce((a, b) => a + b.count, 0) ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="font-mono text-lg font-medium text-ink">Results & Analytics</h1>
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
        <div className="bg-panel border border-rule rounded-sm px-4 py-12 text-center">
          <p className="text-sm font-mono text-ink-soft">loading…</p>
        </div>
      ) : !results ? (
        <div className="border-2 border-dashed border-rule rounded-sm px-4 py-12 text-center">
          <p className="text-sm font-mono text-ink-soft">
            {selectedSub
              ? "no results data yet"
              : "select a subscription to view analytics"}
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          <ScoreBandChart data={results.by_score_band} />
          <RejectionChart
            data={results.rejection_reasons}
            totalApproved={totalApproved}
            totalRejected={totalRejected}
          />
        </div>
      )}
    </div>
  );
}
