"use client"

import { useEffect, useState } from "react"
import { resultsApi, type ResultsData } from "@/lib/api"
import { SubscriptionSelector } from "@/components/SubscriptionSelector"

const CHART_HEIGHT = 120
const CHART_WIDTH = 480
const BAR_GAP = 8

function ScoreBandChart({ data }: { data: ResultsData["by_score_band"] }) {
  if (!data.length) return null
  const maxTotal = Math.max(...data.map(d => d.total), 1)
  const barWidth = (CHART_WIDTH - BAR_GAP * (data.length - 1)) / data.length

  return (
    <div className="overflow-x-auto">
      <svg width={CHART_WIDTH} height={CHART_HEIGHT + 40} className="font-mono text-xs">
        {data.map((band, i) => {
          const x = i * (barWidth + BAR_GAP)
          const totalH = (band.total / maxTotal) * CHART_HEIGHT
          const repliedH = (band.replied / maxTotal) * CHART_HEIGHT
          const rate = band.total > 0 ? Math.round((band.replied / band.total) * 100) : 0

          return (
            <g key={band.band}>
              {/* Total bar (background) */}
              <rect
                x={x}
                y={CHART_HEIGHT - totalH}
                width={barWidth}
                height={totalH}
                fill="#D8EDEB"
                stroke="#C3CDD6"
                strokeWidth={1}
              />
              {/* Replied bar (foreground) */}
              <rect
                x={x}
                y={CHART_HEIGHT - repliedH}
                width={barWidth}
                height={repliedH}
                fill="#106B5E"
              />
              {/* Rate label */}
              <text
                x={x + barWidth / 2}
                y={CHART_HEIGHT - totalH - 4}
                textAnchor="middle"
                fill="#106B5E"
                fontSize={10}
                fontFamily="IBM Plex Mono"
              >
                {rate}%
              </text>
              {/* Band label */}
              <text
                x={x + barWidth / 2}
                y={CHART_HEIGHT + 16}
                textAnchor="middle"
                fill="#4A5A69"
                fontSize={10}
                fontFamily="IBM Plex Mono"
              >
                {band.band}
              </text>
              {/* Total count */}
              <text
                x={x + barWidth / 2}
                y={CHART_HEIGHT + 28}
                textAnchor="middle"
                fill="#4A5A69"
                fontSize={9}
                fontFamily="IBM Plex Mono"
              >
                {band.total}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="flex gap-4 mt-2 text-xs font-mono text-ink-soft">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 inline-block bg-teal-wash border border-rule" /> total
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 inline-block bg-teal" /> replied
        </span>
      </div>
    </div>
  )
}

function RejectionChart({ data }: { data: ResultsData["rejection_reasons"] }) {
  if (!data.length) return null
  const total = data.reduce((s, d) => s + d.count, 0)
  const maxCount = Math.max(...data.map(d => d.count), 1)
  const BAR_H = 20
  const LABEL_W = 160
  const BAR_AREA = 240
  const ROW_GAP = 8

  return (
    <svg
      width={LABEL_W + BAR_AREA + 80}
      height={data.length * (BAR_H + ROW_GAP)}
      className="font-mono text-xs"
    >
      {data.map((row, i) => {
        const y = i * (BAR_H + ROW_GAP)
        const barW = (row.count / maxCount) * BAR_AREA
        const pct = total > 0 ? Math.round((row.count / total) * 100) : 0

        return (
          <g key={row.reason}>
            <text
              x={LABEL_W - 8}
              y={y + BAR_H / 2 + 4}
              textAnchor="end"
              fill="#4A5A69"
              fontSize={11}
              fontFamily="IBM Plex Mono"
            >
              {row.reason.replace(/_/g, " ")}
            </text>
            <rect
              x={LABEL_W}
              y={y}
              width={barW}
              height={BAR_H}
              fill="#B3660C"
              opacity={0.3}
            />
            <rect
              x={LABEL_W}
              y={y}
              width={barW}
              height={BAR_H}
              fill="none"
              stroke="#B3660C"
              strokeWidth={1}
            />
            <text
              x={LABEL_W + barW + 8}
              y={y + BAR_H / 2 + 4}
              fill="#B3660C"
              fontSize={11}
              fontFamily="IBM Plex Mono"
            >
              {row.count} ({pct}%)
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default function ResultsPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [results, setResults] = useState<ResultsData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)
    resultsApi.getResults(subscriptionId)
      .then(setResults)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [subscriptionId])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Results</h1>
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
          <p className="text-ink-soft font-mono text-sm">Select a subscription to view results</p>
        </div>
      )}

      {results && (
        <div className="space-y-6">
          {/* Score band chart */}
          <div className="bg-panel border border-rule p-4">
            <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-4">
              Reply rates by score band
            </div>
            {results.by_score_band.length > 0 ? (
              <ScoreBandChart data={results.by_score_band} />
            ) : (
              <div className="border border-dashed border-rule p-6 text-center">
                <p className="text-ink-soft font-mono text-sm">No score band data yet</p>
              </div>
            )}
          </div>

          {/* Rejection reasons chart */}
          <div className="bg-panel border border-rule p-4">
            <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-4">
              Rejection reasons
            </div>
            {results.rejection_reasons.length > 0 ? (
              <RejectionChart data={results.rejection_reasons} />
            ) : (
              <div className="border border-dashed border-rule p-6 text-center">
                <p className="text-ink-soft font-mono text-sm">No rejections recorded yet</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
