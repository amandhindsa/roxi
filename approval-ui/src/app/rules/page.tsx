"use client";

import { useEffect, useState, useCallback } from "react";
import {
  rulesApi,
  subscriptionsApi,
  type RulesVersion,
  type RulesPreview,
  type Subscription,
} from "@/lib/api";

export default function RulesPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [selectedSub, setSelectedSub] = useState<string>("");
  const [latest, setLatest] = useState<RulesVersion | null>(null);
  const [history, setHistory] = useState<RulesVersion[]>([]);
  const [editText, setEditText] = useState<string>("");
  const [preview, setPreview] = useState<RulesPreview | null>(null);
  const [loadingLatest, setLoadingLatest] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    subscriptionsApi.list().then((subs) => {
      setSubscriptions(subs);
      if (subs.length > 0) setSelectedSub(subs[0].id);
    });
  }, []);

  const fetchLatest = useCallback(async () => {
    if (!selectedSub) return;
    setLoadingLatest(true);
    setError(null);
    try {
      const data = await rulesApi.getLatest(selectedSub);
      setLatest(data);
      setEditText(data.rules_text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load rules");
    } finally {
      setLoadingLatest(false);
    }
  }, [selectedSub]);

  const fetchHistory = useCallback(async () => {
    if (!selectedSub) return;
    setLoadingHistory(true);
    try {
      const data = await rulesApi.list(selectedSub);
      setHistory(data);
    } catch {
      // non-fatal
    } finally {
      setLoadingHistory(false);
    }
  }, [selectedSub]);

  useEffect(() => {
    fetchLatest();
    fetchHistory();
    setPreview(null);
  }, [fetchLatest, fetchHistory]);

  async function handleSave() {
    if (!selectedSub || !editText.trim()) return;
    setSaving(true);
    setError(null);
    setSaveSuccess(false);
    try {
      const saved = await rulesApi.save(selectedSub, editText);
      setLatest(saved);
      setSaveSuccess(true);
      await fetchHistory();
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save rules");
    } finally {
      setSaving(false);
    }
  }

  async function handlePreview() {
    if (!selectedSub || !editText.trim()) return;
    setPreviewing(true);
    setPreview(null);
    setError(null);
    try {
      const result = await rulesApi.preview(selectedSub, editText);
      setPreview(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to preview rules");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleRestore(version: RulesVersion) {
    setRestoring(version.id);
    setEditText(version.rules_text);
    setPreview(null);
    setTimeout(() => setRestoring(null), 500);
  }

  const hasChanges = editText !== (latest?.rules_text ?? "");

  return (
    <div className="space-y-8">
      <div className="flex items-baseline justify-between">
        <h1 className="font-mono text-lg font-medium text-ink">Rules Editor</h1>
        <select
          value={selectedSub}
          onChange={(e) => {
            setSelectedSub(e.target.value);
            setPreview(null);
          }}
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

      {/* Section 1: Current summary */}
      <section>
        <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">
          Current Rules — Version {latest?.version ?? "—"}
        </h2>
        {loadingLatest ? (
          <div className="bg-panel border border-rule rounded-sm px-4 py-6">
            <p className="text-sm font-mono text-ink-soft">loading…</p>
          </div>
        ) : latest ? (
          <div className="bg-panel border border-rule rounded-sm px-4 py-4">
            <p className="text-xs font-mono text-ink-soft mb-2">
              saved {new Date(latest.created_at).toLocaleString()}
              {latest.created_by ? ` by ${latest.created_by}` : ""}
            </p>
            <p className="text-sm font-mono text-ink leading-relaxed whitespace-pre-wrap">
              {latest.rules_text}
            </p>
          </div>
        ) : (
          <div className="border-2 border-dashed border-rule rounded-sm px-4 py-8 text-center">
            <p className="text-sm font-mono text-ink-soft">no rules saved yet</p>
          </div>
        )}
      </section>

      {/* Section 2: Edit area */}
      <section>
        <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">
          Edit Rules
        </h2>
        <div className="space-y-3">
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            placeholder="Write plain-English corrections, e.g. 'Exclude companies with fewer than 10 trucks. Prefer companies in the midwest. Score hiring signals higher if the job title mentions dispatch or fleet.'"
            rows={12}
            className="w-full bg-panel border border-rule rounded-sm px-4 py-3 text-sm font-mono text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal resize-y"
          />
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges || !selectedSub}
              className="bg-teal text-white text-sm font-mono px-4 py-2 rounded-sm hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            >
              {saving ? "saving…" : "Save as new version"}
            </button>
            <button
              onClick={handlePreview}
              disabled={previewing || !editText.trim() || !selectedSub}
              className="bg-panel border border-rule text-sm font-mono text-ink px-4 py-2 rounded-sm hover:bg-ground disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {previewing ? "previewing…" : "Preview"}
            </button>
            {saveSuccess && (
              <span className="text-sm font-mono text-teal">saved successfully</span>
            )}
            {hasChanges && !saveSuccess && (
              <span className="text-xs font-mono text-ink-soft">unsaved changes</span>
            )}
          </div>
        </div>

        {/* Preview result */}
        {preview && (
          <div className="mt-4 bg-panel border border-rule rounded-sm p-4 space-y-3">
            <p className="text-xs font-mono text-ink-soft uppercase tracking-wider">
              Preview result
            </p>
            <div className="flex gap-6">
              <div>
                <p className="text-xs font-mono text-ink-soft">qualified (new rules)</p>
                <p className="text-2xl font-mono font-medium tabular-nums text-ink">
                  {preview.qualified_count}
                </p>
              </div>
              <div>
                <p className="text-xs font-mono text-ink-soft">qualified (current rules)</p>
                <p className="text-2xl font-mono font-medium tabular-nums text-ink">
                  {preview.previous_count}
                </p>
              </div>
              <div>
                <p className="text-xs font-mono text-ink-soft">delta</p>
                <p
                  className={`text-2xl font-mono font-medium tabular-nums ${
                    preview.qualified_count - preview.previous_count >= 0
                      ? "text-teal"
                      : "text-amber"
                  }`}
                >
                  {preview.qualified_count - preview.previous_count >= 0 ? "+" : ""}
                  {preview.qualified_count - preview.previous_count}
                </p>
              </div>
            </div>
            {preview.added.length > 0 && (
              <div>
                <p className="text-xs font-mono text-teal mb-1">
                  would add ({preview.added.length})
                </p>
                <ul className="space-y-0.5">
                  {preview.added.map((c, i) => (
                    <li key={i} className="text-xs font-mono text-ink">
                      + {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {preview.removed.length > 0 && (
              <div>
                <p className="text-xs font-mono text-amber mb-1">
                  would remove ({preview.removed.length})
                </p>
                <ul className="space-y-0.5">
                  {preview.removed.map((c, i) => (
                    <li key={i} className="text-xs font-mono text-ink">
                      - {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Section 3: Version history */}
      <section>
        <h2 className="font-mono text-xs uppercase tracking-wider text-ink-soft mb-3">
          Version History
        </h2>
        {loadingHistory ? (
          <div className="bg-panel border border-rule rounded-sm px-4 py-4">
            <p className="text-sm font-mono text-ink-soft">loading…</p>
          </div>
        ) : history.length === 0 ? (
          <div className="border-2 border-dashed border-rule rounded-sm px-4 py-8 text-center">
            <p className="text-sm font-mono text-ink-soft">no version history yet</p>
          </div>
        ) : (
          <div className="bg-panel border border-rule rounded-sm overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-rule text-ink-soft">
                  {["version", "date", "excerpt", ""].map((h, i) => (
                    <th
                      key={i}
                      className="px-3 py-2 text-left font-medium uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {history.map((v) => (
                  <tr
                    key={v.id}
                    className={`hover:bg-ground transition-colors ${
                      v.id === latest?.id ? "bg-teal-wash" : ""
                    }`}
                  >
                    <td className="px-3 py-2.5 tabular-nums text-ink font-medium">
                      v{v.version}
                      {v.id === latest?.id && (
                        <span className="ml-2 text-teal text-[10px]">current</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-ink-soft whitespace-nowrap">
                      {new Date(v.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5 text-ink-soft max-w-sm truncate">
                      {v.rules_text.slice(0, 100)}
                      {v.rules_text.length > 100 ? "…" : ""}
                    </td>
                    <td className="px-3 py-2.5">
                      <button
                        onClick={() => handleRestore(v)}
                        disabled={restoring === v.id || v.id === latest?.id}
                        className="text-teal text-xs font-mono underline underline-offset-2 hover:opacity-70 disabled:opacity-40 disabled:no-underline"
                      >
                        {restoring === v.id ? "restoring…" : "Restore"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
