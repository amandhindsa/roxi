"use client"

import { useEffect, useState } from "react"
import { teamApi, suppressionApi, subscriptionsApi, type Member, type SuppressionEntry, type Subscription } from "@/lib/api"
import { SubscriptionSelector } from "@/components/SubscriptionSelector"
import { createBrowserClient } from "@/lib/supabase"

type Tab = "team" | "sending" | "suppression" | "limits" | "data"

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Tokyo",
  "Australia/Sydney",
]

export default function SettingsPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [tab, setTab] = useState<Tab>("team")
  const [orgId, setOrgId] = useState<string | null>(null)

  // Team
  const [members, setMembers] = useState<Member[]>([])
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteRole, setInviteRole] = useState<"reviewer" | "viewer">("reviewer")
  const [inviting, setInviting] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  const [currentUserEmail, setCurrentUserEmail] = useState<string | null>(null)
  const [currentMemberRole, setCurrentMemberRole] = useState<string | null>(null)

  // Sending
  const [apiKey, setApiKey] = useState("")
  const [campaignId, setCampaignId] = useState("")
  const [savingSending, setSavingSending] = useState(false)

  // Suppression
  const [suppressions, setSuppressions] = useState<SuppressionEntry[]>([])
  const [newContact, setNewContact] = useState("")
  const [addingContact, setAddingContact] = useState(false)
  const [removingContact, setRemovingContact] = useState<string | null>(null)

  // Limits
  const [spendCeiling, setSpendCeiling] = useState("")
  const [dailyBudget, setDailyBudget] = useState("")
  const [deliveryHour, setDeliveryHour] = useState("")
  const [deliveryTz, setDeliveryTz] = useState("America/New_York")
  const [paused, setPaused] = useState(false)
  const [savingLimits, setSavingLimits] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Get current user
  useEffect(() => {
    const client = createBrowserClient()
    client.auth.getUser().then(({ data }) => {
      setCurrentUserEmail(data.user?.email ?? null)
    })
  }, [])

  // Load subscription data when subscriptionId changes
  useEffect(() => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)
    subscriptionsApi.get(subscriptionId)
      .then(sub => {
        setSubscription(sub)
        setOrgId(sub.org_id)
        setApiKey(sub.sending?.api_key ?? "")
        setCampaignId(sub.sending?.campaign_id ?? "")
        setSpendCeiling(sub.settings.spend_ceiling_usd != null ? String(sub.settings.spend_ceiling_usd) : "")
        setDailyBudget(sub.settings.daily_research_budget != null ? String(sub.settings.daily_research_budget) : "")
        setDeliveryHour(sub.settings.delivery_hour != null ? String(sub.settings.delivery_hour) : "")
        setDeliveryTz(sub.settings.delivery_timezone ?? "America/New_York")
        setPaused(sub.status === "paused")
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [subscriptionId])

  // Load tab-specific data
  useEffect(() => {
    if (!subscriptionId || !orgId) return
    if (tab === "team") {
      teamApi.getMembers(orgId).then(m => {
        setMembers(m)
        const me = m.find(member => member.email === currentUserEmail)
        setCurrentMemberRole(me?.role ?? null)
      }).catch(() => {})
    }
    if (tab === "suppression") {
      suppressionApi.list(subscriptionId).then(setSuppressions).catch(() => {})
    }
  }, [tab, subscriptionId, orgId, currentUserEmail])

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(null), 3000)
  }

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!orgId || !inviteEmail) return
    setInviting(true)
    try {
      const m = await teamApi.inviteMember(orgId, inviteEmail, inviteRole)
      setMembers(prev => [...prev, m])
      setInviteEmail("")
      showSuccess("Invite sent")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invite failed")
    } finally {
      setInviting(false)
    }
  }

  const handleRemoveMember = async (member: Member) => {
    if (!orgId) return
    setRemoving(member.id)
    try {
      await teamApi.removeMember(orgId, member.id)
      setMembers(prev => prev.filter(m => m.id !== member.id))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Remove failed")
    } finally {
      setRemoving(null)
    }
  }

  const handleSaveSending = async () => {
    if (!subscriptionId) return
    setSavingSending(true)
    try {
      await subscriptionsApi.update(subscriptionId, {
        sending: { tool: "Instantly", api_key: apiKey, campaign_id: campaignId }
      })
      showSuccess("Sending settings saved")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed")
    } finally {
      setSavingSending(false)
    }
  }

  const handleAddContact = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!subscriptionId || !newContact.trim()) return
    setAddingContact(true)
    try {
      const entry = await suppressionApi.add(subscriptionId, newContact.trim())
      setSuppressions(prev => [...prev, entry])
      setNewContact("")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Add failed")
    } finally {
      setAddingContact(false)
    }
  }

  const handleRemoveContact = async (entry: SuppressionEntry) => {
    if (!subscriptionId) return
    setRemovingContact(entry.id)
    try {
      await suppressionApi.remove(subscriptionId, entry.id)
      setSuppressions(prev => prev.filter(s => s.id !== entry.id))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Remove failed")
    } finally {
      setRemovingContact(null)
    }
  }

  const handleSaveLimits = async () => {
    if (!subscriptionId) return
    setSavingLimits(true)
    try {
      await subscriptionsApi.update(subscriptionId, {
        status: paused ? "paused" : "active",
        settings: {
          spend_ceiling_usd: spendCeiling ? Number(spendCeiling) : null,
          daily_research_budget: dailyBudget ? Number(dailyBudget) : null,
          delivery_hour: deliveryHour ? Number(deliveryHour) : null,
          delivery_timezone: deliveryTz,
          lead_retention_days: subscription?.settings.lead_retention_days ?? null,
        }
      })
      showSuccess("Limits saved")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed")
    } finally {
      setSavingLimits(false)
    }
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: "team", label: "Team" },
    { id: "sending", label: "Sending" },
    { id: "suppression", label: "Suppression" },
    { id: "limits", label: "Limits" },
    { id: "data", label: "Data" },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Settings</h1>
        <SubscriptionSelector value={subscriptionId} onChange={setSubscriptionId} />
      </div>

      {loading && <p className="text-ink-soft font-mono text-sm">loading…</p>}

      {error && (
        <div className="border border-amber bg-amber-wash px-4 py-2 mb-4">
          <p className="text-amber font-mono text-sm">{error}</p>
          <button onClick={() => setError(null)} className="text-xs font-mono text-amber mt-1">dismiss</button>
        </div>
      )}

      {successMsg && (
        <div className="border border-teal bg-teal-wash px-4 py-2 mb-4">
          <p className="text-teal font-mono text-sm">{successMsg}</p>
        </div>
      )}

      {!subscriptionId && !loading && (
        <div className="border border-dashed border-rule p-10 text-center">
          <p className="text-ink-soft font-mono text-sm">Select a subscription to manage settings</p>
        </div>
      )}

      {subscriptionId && !loading && (
        <>
          {/* Tabs */}
          <div className="flex gap-0 border-b border-rule mb-6">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => { setTab(t.id); setError(null) }}
                className={`px-4 py-2 text-xs font-mono border-b-2 transition-colors ${
                  tab === t.id
                    ? "border-teal text-teal font-bold"
                    : "border-transparent text-ink-soft hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Team tab */}
          {tab === "team" && (
            <div className="space-y-4">
              <div className="bg-panel border border-rule">
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="border-b border-rule text-left">
                      <th className="px-4 py-2 text-xs text-ink-soft font-medium">email</th>
                      <th className="px-4 py-2 text-xs text-ink-soft font-medium">role</th>
                      <th className="px-4 py-2 text-xs text-ink-soft font-medium"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.length === 0 && (
                      <tr>
                        <td colSpan={3} className="px-4 py-4 text-ink-soft text-xs text-center">No members</td>
                      </tr>
                    )}
                    {members.map(m => (
                      <tr key={m.id} className="border-b border-rule last:border-0">
                        <td className="px-4 py-2 text-ink">{m.email}</td>
                        <td className="px-4 py-2 text-ink-soft">{m.role}</td>
                        <td className="px-4 py-2">
                          {m.email !== currentUserEmail && currentMemberRole === "owner" && (
                            <button
                              onClick={() => handleRemoveMember(m)}
                              disabled={removing === m.id}
                              className="text-xs font-mono text-amber hover:opacity-70 disabled:opacity-50"
                            >
                              {removing === m.id ? "removing…" : "remove"}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {currentMemberRole === "owner" && (
                <div className="bg-panel border border-rule p-4">
                  <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-3">Invite member</div>
                  <form onSubmit={handleInvite} className="flex gap-2 flex-wrap items-end">
                    <div className="flex flex-col gap-1 flex-1 min-w-[200px]">
                      <label className="text-xs font-mono text-ink-soft">Email</label>
                      <input
                        type="email"
                        value={inviteEmail}
                        onChange={e => setInviteEmail(e.target.value)}
                        required
                        placeholder="colleague@company.com"
                        className="border border-rule bg-ground px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-ink"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-mono text-ink-soft">Role</label>
                      <select
                        value={inviteRole}
                        onChange={e => setInviteRole(e.target.value as "reviewer" | "viewer")}
                        className="border border-rule bg-ground px-3 py-1.5 text-sm font-mono focus:outline-none"
                      >
                        <option value="reviewer">reviewer</option>
                        <option value="viewer">viewer</option>
                      </select>
                    </div>
                    <button
                      type="submit"
                      disabled={inviting}
                      className="px-4 py-1.5 bg-teal text-white text-xs font-mono hover:opacity-90 disabled:opacity-50"
                    >
                      {inviting ? "sending…" : "invite"}
                    </button>
                  </form>
                </div>
              )}
            </div>
          )}

          {/* Sending tab */}
          {tab === "sending" && (
            <div className="bg-panel border border-rule p-4 space-y-4 max-w-md">
              <div>
                <label className="text-xs font-mono text-ink-soft block mb-1">Tool</label>
                <input
                  type="text"
                  value="Instantly"
                  readOnly
                  className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono text-ink-soft cursor-not-allowed"
                />
              </div>
              <div>
                <label className="text-xs font-mono text-ink-soft block mb-1">API Key</label>
                <input
                  type="text"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="inst_..."
                  className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
                />
              </div>
              <div>
                <label className="text-xs font-mono text-ink-soft block mb-1">Campaign ID</label>
                <input
                  type="text"
                  value={campaignId}
                  onChange={e => setCampaignId(e.target.value)}
                  placeholder="campaign-uuid"
                  className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
                />
              </div>
              <button
                onClick={handleSaveSending}
                disabled={savingSending}
                className="px-4 py-2 bg-teal text-white text-xs font-mono hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {savingSending ? "saving…" : "save"}
              </button>
            </div>
          )}

          {/* Suppression tab */}
          {tab === "suppression" && (
            <div className="space-y-4">
              <form onSubmit={handleAddContact} className="flex gap-2 items-end">
                <div className="flex flex-col gap-1 flex-1">
                  <label className="text-xs font-mono text-ink-soft">Add contact to suppression list</label>
                  <input
                    type="text"
                    value={newContact}
                    onChange={e => setNewContact(e.target.value)}
                    placeholder="email@domain.com or domain.com"
                    className="border border-rule bg-ground px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-ink"
                  />
                </div>
                <button
                  type="submit"
                  disabled={addingContact || !newContact.trim()}
                  className="px-4 py-1.5 bg-teal text-white text-xs font-mono hover:opacity-90 disabled:opacity-50"
                >
                  {addingContact ? "adding…" : "add"}
                </button>
              </form>

              {suppressions.length === 0 ? (
                <div className="border border-dashed border-rule p-8 text-center">
                  <p className="text-ink-soft font-mono text-sm">No suppressed contacts</p>
                </div>
              ) : (
                <div className="bg-panel border border-rule">
                  <table className="w-full text-sm font-mono">
                    <thead>
                      <tr className="border-b border-rule text-left">
                        <th className="px-4 py-2 text-xs text-ink-soft font-medium">contact</th>
                        <th className="px-4 py-2 text-xs text-ink-soft font-medium">added</th>
                        <th className="px-4 py-2 text-xs text-ink-soft font-medium"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {suppressions.map(entry => (
                        <tr key={entry.id} className="border-b border-rule last:border-0">
                          <td className="px-4 py-2 text-ink">{entry.contact}</td>
                          <td className="px-4 py-2 text-ink-soft text-xs">
                            {new Date(entry.created_at).toLocaleDateString()}
                          </td>
                          <td className="px-4 py-2">
                            <button
                              onClick={() => handleRemoveContact(entry)}
                              disabled={removingContact === entry.id}
                              className="text-xs font-mono text-amber hover:opacity-70 disabled:opacity-50"
                            >
                              {removingContact === entry.id ? "removing…" : "remove"}
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

          {/* Limits tab */}
          {tab === "limits" && (
            <div className="bg-panel border border-rule p-4 space-y-4 max-w-md">
              <div>
                <label className="text-xs font-mono text-ink-soft block mb-1">Spend ceiling (USD/mo)</label>
                <input
                  type="number"
                  value={spendCeiling}
                  onChange={e => setSpendCeiling(e.target.value)}
                  placeholder="500"
                  min={0}
                  className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
                />
              </div>
              <div>
                <label className="text-xs font-mono text-ink-soft block mb-1">Daily research budget (USD)</label>
                <input
                  type="number"
                  value={dailyBudget}
                  onChange={e => setDailyBudget(e.target.value)}
                  placeholder="50"
                  min={0}
                  className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
                />
              </div>
              <div>
                <label className="text-xs font-mono text-ink-soft block mb-1">Delivery hour (0–23)</label>
                <input
                  type="number"
                  value={deliveryHour}
                  onChange={e => setDeliveryHour(e.target.value)}
                  placeholder="9"
                  min={0}
                  max={23}
                  className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
                />
              </div>
              <div>
                <label className="text-xs font-mono text-ink-soft block mb-1">Delivery timezone</label>
                <select
                  value={deliveryTz}
                  onChange={e => setDeliveryTz(e.target.value)}
                  className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
                >
                  {TIMEZONES.map(tz => (
                    <option key={tz} value={tz}>{tz}</option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setPaused(v => !v)}
                  className={`relative w-10 h-5 rounded-full transition-colors ${paused ? "bg-amber" : "bg-teal"}`}
                  aria-label={paused ? "Resume" : "Pause"}
                >
                  <span
                    className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                      paused ? "translate-x-5" : "translate-x-0.5"
                    }`}
                  />
                </button>
                <span className="text-sm font-mono text-ink-soft">
                  {paused ? "Paused" : "Active"}
                </span>
              </div>
              <button
                onClick={handleSaveLimits}
                disabled={savingLimits}
                className="px-4 py-2 bg-teal text-white text-xs font-mono hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {savingLimits ? "saving…" : "save"}
              </button>
            </div>
          )}

          {/* Data tab */}
          {tab === "data" && (
            <div className="bg-panel border border-rule p-4 max-w-md">
              <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-3">Data retention</div>
              <div className="space-y-3">
                <div className="flex justify-between items-center border-b border-rule pb-2">
                  <span className="text-sm font-mono text-ink-soft">Lead retention period</span>
                  <span className="text-sm font-mono text-ink">
                    {subscription?.settings.lead_retention_days != null
                      ? `${subscription.settings.lead_retention_days} days`
                      : "not set"}
                  </span>
                </div>
                <p className="text-xs font-mono text-ink-soft">
                  Leads older than the retention period are automatically purged. Contact support to change this setting.
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
