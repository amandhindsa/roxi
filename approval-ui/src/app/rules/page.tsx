"use client"

import { useEffect, useState } from "react"
import { rulesApi, type RulesVersion, type RulesPreview } from "@/lib/api"
import { SubscriptionSelector } from "@/components/SubscriptionSelector"

export default function RulesPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [latest, setLatest] = useState<RulesVersion | null>(null)
  const [history, setHistory] = useState<RulesVersion[]>([])
  const [editText, setEditText] = useState("")
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState<RulesPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)
    Promise.all([
      rulesApi.getLatest(subscriptionId).catch(() => null),
      rulesApi.list(subscriptionId).catch(() => []),
    ]).then(([lat, hist]) => {
      setLatest(lat)
      setHistory(hist)
      setEditText(lat?.rules_text ?? "")
    }).catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [subscriptionId])

  const handleSave = async () => {
    if (!subscriptionId || !editText.trim()) return
    setSaving(true)
    setError(null)
    setSaveSuccess(false)
    try {
      const saved = await rulesApi.save(subscriptionId, editText)
      setLatest(saved)
      setHistory(prev => [saved, ...prev])
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  const handlePreview = async () => {
    if (!subscriptionId || !editText.trim()) return
    setPreviewing(true)
    setPreview(null)
    try {
      const result = await rulesApi.preview(subscriptionId, editText)
      setPreview(result)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Preview failed")
    } finally {
      setPreviewing(false)
    }
  }

  const handleRestore = (version: RulesVersion) => {
    setEditText(version.rules_text)
    setPreview(null)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Rules editor</h1>
        <SubscriptionSelector value={subscriptionId} onChange={setSubscriptionId} />
      </div>

      {loading && <p className="text-ink-soft font-mono text-sm">loading…</p>}

      {error && (
        <div className="border border-amber bg-amber-wash px-4 py-2 mb-4">
          <p className="text-amber font-mono text-sm">{error}</p>
        </div>
      )}

      {subscriptionId && !loading && (
        <div className="space-y-6">
          {/* Current rules */}
          {latest && (
            <div className="bg-panel border border-rule p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono text-ink-soft uppercase tracking-wide">
                  Current rules — version {latest.version}
                </span>
                <span className="text-xs font-mono text-ink-soft">{formatDate(latest.created_at)}</span>
              </div>
              <pre className="text-sm font-mono text-ink whitespace-pre-wrap bg-ground border border-rule p-3">
                {latest.rules_text}
              </pre>
            </div>
          )}

          {!latest && (
            <div className="border border-dashed border-rule p-8 text-center">
              <p className="text-ink-soft font-mono text-sm">No rules saved yet. Write the first version below.</p>
            </div>
          )}

          {/* Edit */}
          <div className="bg-panel border border-rule p-4">
            <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-3">
              Edit rules
            </div>
            <textarea
              value={editText}
              onChange={e => setEditText(e.target.value)}
              rows={14}
              placeholder="Write rules in plain English. Example:
- Minimum fleet size: 10 trucks
- Exclude fleets over 500 trucks
- Require US-based companies
- Prioritize hiring signals (+20)
- Pain complaints about ELD get +15"
              className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono text-ink focus:outline-none focus:border-ink resize-y"
            />

            {/* Preview result */}
            {preview && (
              <div className="mt-3 bg-ground border border-rule p-3">
                <div className="text-xs font-mono text-ink-soft mb-2 uppercase tracking-wide">Preview result</div>
                <p className="text-sm font-mono text-ink">
                  With these rules:{" "}
                  <strong>{preview.qualified_count}</strong> qualified (was {preview.previous_count})
                </p>
                {preview.added.length > 0 && (
                  <div className="mt-2">
                    <span className="text-xs font-mono text-teal">Added: </span>
                    <span className="text-xs font-mono text-ink">{preview.added.join(", ")}</span>
                  </div>
                )}
                {preview.removed.length > 0 && (
                  <div className="mt-1">
                    <span className="text-xs font-mono text-amber">Removed: </span>
                    <span className="text-xs font-mono text-ink">{preview.removed.join(", ")}</span>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2 mt-3">
              <button
                onClick={handleSave}
                disabled={saving || !editText.trim()}
                className="px-4 py-2 bg-teal text-white text-xs font-mono hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {saving ? "saving…" : "save as new version"}
              </button>
              <button
                onClick={handlePreview}
                disabled={previewing || !editText.trim()}
                className="px-4 py-2 border border-rule text-xs font-mono text-ink-soft hover:text-ink disabled:opacity-50 transition-colors"
              >
                {previewing ? "previewing…" : "preview"}
              </button>
              {saveSuccess && (
                <span className="text-xs font-mono text-teal self-center">Saved!</span>
              )}
            </div>
          </div>

          {/* Version history */}
          {history.length > 0 && (
            <div className="bg-panel border border-rule p-4">
              <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-3">Version history</div>
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-rule text-left">
                    <th className="py-1.5 pr-4 text-ink-soft font-medium">version</th>
                    <th className="py-1.5 pr-4 text-ink-soft font-medium">date</th>
                    <th className="py-1.5 pr-4 text-ink-soft font-medium">created by</th>
                    <th className="py-1.5 text-ink-soft font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {history.map(v => (
                    <tr key={v.id} className="border-b border-rule">
                      <td className="py-1.5 pr-4 text-ink">v{v.version}</td>
                      <td className="py-1.5 pr-4 text-ink-soft">{formatDate(v.created_at)}</td>
                      <td className="py-1.5 pr-4 text-ink-soft">{v.created_by ?? "—"}</td>
                      <td className="py-1.5">
                        <button
                          onClick={() => handleRestore(v)}
                          className="text-teal hover:opacity-70 transition-opacity"
                        >
                          restore
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {!subscriptionId && !loading && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">Select a subscription to manage rules</p>
        </div>
      )}
    </div>
  )
}
