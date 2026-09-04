"use client";

import { useEffect, useState, useCallback } from "react";
import { subscriptionsApi, teamApi, suppressionApi } from "@/lib/api";
import type { Subscription, Member, SuppressionEntry } from "@/lib/api";

type Tab = "team" | "sending" | "suppression" | "limits";

const TIMEZONES = [
  "America/Toronto",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "UTC",
];

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-xs font-mono font-medium border-b-2 transition-colors ${
        active
          ? "border-teal text-teal"
          : "border-transparent text-ink-soft hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function RoleBadge({ role }: { role: string }) {
  const cls =
    role === "owner"
      ? "bg-teal-wash text-teal"
      : role === "reviewer"
      ? "bg-amber-wash text-amber"
      : "bg-ground text-ink-soft";
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-mono ${cls}`}>
      {role}
    </span>
  );
}

function Banner({
  message,
  type,
  onDismiss,
}: {
  message: string;
  type: "success" | "error";
  onDismiss: () => void;
}) {
  const cls =
    type === "success"
      ? "bg-teal-wash border-teal text-teal"
      : "bg-red-50 border-red-300 text-red-700";
  return (
    <div className={`flex items-center justify-between border px-4 py-3 rounded-sm text-sm font-mono ${cls}`}>
      <span>{message}</span>
      <button onClick={onDismiss} className="ml-4 opacity-60 hover:opacity-100 text-xs">
        dismiss
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("team");
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [suppression, setSuppression] = useState<SuppressionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [banner, setBanner] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // Team state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("reviewer");
  const [inviting, setInviting] = useState(false);

  // Sending state
  const [instantlyKey, setInstantlyKey] = useState("");
  const [instantlyCampaignId, setInstantlyCampaignId] = useState("");
  const [savingSending, setSavingSending] = useState(false);

  // Suppression state
  const [suppressContact, setSuppressContact] = useState("");
  const [suppressChannel, setSuppressChannel] = useState("email");
  const [addingSuppression, setAddingSuppression] = useState(false);

  // Limits state
  const [spendCeiling, setSpendCeiling] = useState("");
  const [dailyBudget, setDailyBudget] = useState("");
  const [deliveryHour, setDeliveryHour] = useState("");
  const [timezone, setTimezone] = useState("America/Toronto");
  const [paused, setPaused] = useState(false);
  const [savingLimits, setSavingLimits] = useState(false);

  const showBanner = (message: string, type: "success" | "error") => {
    setBanner({ message, type });
    setTimeout(() => setBanner(null), 5000);
  };

  const loadData = useCallback(async () => {
    try {
      const subs = await subscriptionsApi.list();
      const sub = subs[0] ?? null;
      setSubscription(sub);

      if (sub) {
        setInstantlyKey(sub.sending?.api_key ?? "");
        setInstantlyCampaignId(sub.sending?.campaign_id ?? "");
        setSpendCeiling(sub.settings.spend_ceiling_usd?.toString() ?? "");
        setDailyBudget(sub.settings.daily_research_budget?.toString() ?? "");
        setDeliveryHour(sub.settings.delivery_hour?.toString() ?? "");
        setTimezone(sub.settings.delivery_timezone ?? "America/Toronto");
        setPaused(sub.status === "paused");

        const orgMembers = await teamApi.getMembers(sub.org_id);
        setMembers(orgMembers);

        const suppressionList = await suppressionApi.list(sub.id);
        setSuppression(suppressionList);
      }
    } catch {
      // silently fail on initial load
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Determine current user role (assume first owner is current user for now)
  const currentUserIsOwner = members.some((m) => m.role === "owner");

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!subscription || !inviteEmail.trim()) return;
    setInviting(true);
    try {
      const newMember = await teamApi.inviteMember(subscription.org_id, inviteEmail.trim(), inviteRole);
      setMembers((prev) => [...prev, newMember]);
      setInviteEmail("");
      showBanner("Invitation sent.", "success");
    } catch (err) {
      showBanner((err as Error).message || "Failed to send invitation.", "error");
    } finally {
      setInviting(false);
    }
  }

  async function handleRemoveMember(member: Member) {
    if (!subscription) return;
    try {
      await teamApi.removeMember(subscription.org_id, member.user_id);
      setMembers((prev) => prev.filter((m) => m.id !== member.id));
      showBanner("Member removed.", "success");
    } catch (err) {
      showBanner((err as Error).message || "Failed to remove member.", "error");
    }
  }

  async function handleSaveSending(e: React.FormEvent) {
    e.preventDefault();
    if (!subscription) return;
    setSavingSending(true);
    try {
      const updated = await subscriptionsApi.update(subscription.id, {
        sending: {
          tool: "instantly",
          api_key: instantlyKey || null,
          campaign_id: instantlyCampaignId || null,
        },
      });
      setSubscription(updated);
      showBanner("Sending settings saved.", "success");
    } catch (err) {
      showBanner((err as Error).message || "Failed to save sending settings.", "error");
    } finally {
      setSavingSending(false);
    }
  }

  async function handleAddSuppression(e: React.FormEvent) {
    e.preventDefault();
    if (!subscription || !suppressContact.trim()) return;
    setAddingSuppression(true);
    try {
      const entry = await suppressionApi.add(subscription.id, suppressContact.trim());
      setSuppression((prev) => [...prev, entry]);
      setSuppressContact("");
      showBanner("Contact suppressed.", "success");
    } catch (err) {
      showBanner((err as Error).message || "Failed to add suppression.", "error");
    } finally {
      setAddingSuppression(false);
    }
  }

  async function handleRemoveSuppression(entry: SuppressionEntry) {
    if (!subscription) return;
    try {
      await suppressionApi.remove(subscription.id, entry.id);
      setSuppression((prev) => prev.filter((s) => s.id !== entry.id));
      showBanner("Suppression removed.", "success");
    } catch (err) {
      showBanner((err as Error).message || "Failed to remove suppression.", "error");
    }
  }

  async function handleSaveLimits(e: React.FormEvent) {
    e.preventDefault();
    if (!subscription) return;
    setSavingLimits(true);
    try {
      const updated = await subscriptionsApi.update(subscription.id, {
        status: paused ? "paused" : "active",
        settings: {
          spend_ceiling_usd: spendCeiling ? parseFloat(spendCeiling) : null,
          daily_research_budget: dailyBudget ? parseInt(dailyBudget) : null,
          delivery_hour: deliveryHour ? parseInt(deliveryHour) : null,
          delivery_timezone: timezone || null,
          lead_retention_days: subscription.settings.lead_retention_days,
        },
      });
      setSubscription(updated);
      showBanner("Limits saved.", "success");
    } catch (err) {
      showBanner((err as Error).message || "Failed to save limits.", "error");
    } finally {
      setSavingLimits(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="text-sm font-mono text-ink-soft">Loading settings…</span>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-baseline justify-between">
        <h1 className="font-mono text-lg font-medium text-ink">Settings</h1>
        {subscription && (
          <span className="text-xs font-mono text-ink-soft">{subscription.name}</span>
        )}
      </div>

      {banner && (
        <Banner
          message={banner.message}
          type={banner.type}
          onDismiss={() => setBanner(null)}
        />
      )}

      {/* Tab bar */}
      <div className="border-b border-rule flex gap-0">
        {(["team", "sending", "suppression", "limits"] as Tab[]).map((tab) => (
          <TabButton key={tab} active={activeTab === tab} onClick={() => setActiveTab(tab)}>
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </TabButton>
        ))}
      </div>

      {/* Tab: Team */}
      {activeTab === "team" && (
        <div className="space-y-6">
          <div className="bg-panel border border-rule rounded-sm overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-rule text-ink-soft">
                  {["email", "role", "actions"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left font-medium uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {members.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-4 py-6 text-ink-soft text-center">
                      No members found.
                    </td>
                  </tr>
                ) : (
                  members.map((member) => (
                    <tr key={member.id} className="hover:bg-ground transition-colors">
                      <td className="px-4 py-2.5 text-ink">{member.email}</td>
                      <td className="px-4 py-2.5">
                        <RoleBadge role={member.role} />
                      </td>
                      <td className="px-4 py-2.5">
                        {member.role !== "owner" && currentUserIsOwner && (
                          <button
                            onClick={() => handleRemoveMember(member)}
                            className="text-ink-soft hover:text-red-600 transition-colors underline underline-offset-2"
                          >
                            remove
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {currentUserIsOwner && (
            <div className="bg-panel border border-rule rounded-sm p-4">
              <h3 className="text-xs font-mono font-medium text-ink-soft uppercase tracking-wider mb-3">
                Invite member
              </h3>
              <form onSubmit={handleInvite} className="flex gap-2 flex-wrap">
                <input
                  type="email"
                  placeholder="email@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  className="flex-1 min-w-48 px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal"
                />
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink focus:outline-none focus:border-teal"
                >
                  <option value="owner">owner</option>
                  <option value="reviewer">reviewer</option>
                  <option value="viewer">viewer</option>
                </select>
                <button
                  type="submit"
                  disabled={inviting}
                  className="px-4 py-1.5 text-sm font-mono bg-teal text-white rounded-sm hover:bg-teal/90 disabled:opacity-50 transition-colors"
                >
                  {inviting ? "Inviting…" : "Invite"}
                </button>
              </form>
            </div>
          )}
        </div>
      )}

      {/* Tab: Sending */}
      {activeTab === "sending" && (
        <div className="space-y-4">
          <div className="bg-ground p-4 border border-rule rounded-sm">
            <p className="text-sm font-mono text-ink-soft leading-relaxed">
              Roxi hands approved leads to your sending tool. Connect your Instantly account
              to queue approved leads automatically.
            </p>
          </div>

          <form onSubmit={handleSaveSending} className="space-y-4 bg-panel border border-rule rounded-sm p-4">
            <div className="space-y-1">
              <label className="block text-xs font-mono text-ink-soft uppercase tracking-wider">
                Instantly API key
              </label>
              <div className="flex gap-2">
                <input
                  type="password"
                  placeholder="sk-…"
                  value={instantlyKey}
                  onChange={(e) => setInstantlyKey(e.target.value)}
                  className="flex-1 px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-mono text-ink-soft uppercase tracking-wider">
                Campaign ID
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="campaign_…"
                  value={instantlyCampaignId}
                  onChange={(e) => setInstantlyCampaignId(e.target.value)}
                  className="flex-1 px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={savingSending}
              className="px-4 py-1.5 text-sm font-mono bg-teal text-white rounded-sm hover:bg-teal/90 disabled:opacity-50 transition-colors"
            >
              {savingSending ? "Saving…" : "Save sending settings"}
            </button>
          </form>
        </div>
      )}

      {/* Tab: Suppression */}
      {activeTab === "suppression" && (
        <div className="space-y-4">
          <div className="bg-panel border border-rule rounded-sm overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-rule text-ink-soft">
                  {["contact", "added", "actions"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left font-medium uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {suppression.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center">
                      <div className="border border-dashed border-rule rounded-sm py-6 mx-4">
                        <p className="text-ink-soft font-mono text-xs">No suppressed contacts</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  suppression.map((entry) => (
                    <tr key={entry.id} className="hover:bg-ground transition-colors">
                      <td className="px-4 py-2.5 text-ink">{entry.contact}</td>
                      <td className="px-4 py-2.5 text-ink-soft tabular-nums">
                        {new Date(entry.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2.5">
                        <button
                          onClick={() => handleRemoveSuppression(entry)}
                          className="text-ink-soft hover:text-red-600 transition-colors underline underline-offset-2"
                        >
                          remove
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="bg-panel border border-rule rounded-sm p-4">
            <h3 className="text-xs font-mono font-medium text-ink-soft uppercase tracking-wider mb-3">
              Add suppression
            </h3>
            <form onSubmit={handleAddSuppression} className="flex gap-2 flex-wrap">
              <input
                type="text"
                placeholder="email or phone"
                value={suppressContact}
                onChange={(e) => setSuppressContact(e.target.value)}
                required
                className="flex-1 min-w-48 px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal"
              />
              <select
                value={suppressChannel}
                onChange={(e) => setSuppressChannel(e.target.value)}
                className="px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink focus:outline-none focus:border-teal"
              >
                <option value="email">email</option>
                <option value="whatsapp">whatsapp</option>
                <option value="all">all</option>
              </select>
              <button
                type="submit"
                disabled={addingSuppression}
                className="px-4 py-1.5 text-sm font-mono bg-teal text-white rounded-sm hover:bg-teal/90 disabled:opacity-50 transition-colors"
              >
                {addingSuppression ? "Adding…" : "Add"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Tab: Limits */}
      {activeTab === "limits" && (
        <form onSubmit={handleSaveLimits} className="space-y-4 bg-panel border border-rule rounded-sm p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-xs font-mono text-ink-soft uppercase tracking-wider">
                Spend ceiling ($/day)
              </label>
              <input
                type="number"
                step="0.50"
                min="0.50"
                placeholder="e.g. 5.00"
                value={spendCeiling}
                onChange={(e) => setSpendCeiling(e.target.value)}
                className="w-full px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-mono text-ink-soft uppercase tracking-wider">
                Daily research budget (leads)
              </label>
              <input
                type="number"
                min="1"
                max="50"
                placeholder="e.g. 10"
                value={dailyBudget}
                onChange={(e) => setDailyBudget(e.target.value)}
                className="w-full px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-mono text-ink-soft uppercase tracking-wider">
                Delivery hour (0–23)
              </label>
              <input
                type="number"
                min="0"
                max="23"
                placeholder="e.g. 9"
                value={deliveryHour}
                onChange={(e) => setDeliveryHour(e.target.value)}
                className="w-full px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-mono text-ink-soft uppercase tracking-wider">
                Timezone
              </label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full px-3 py-1.5 text-sm font-mono bg-ground border border-rule rounded-sm text-ink focus:outline-none focus:border-teal"
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-1">
            <input
              id="paused"
              type="checkbox"
              checked={paused}
              onChange={(e) => setPaused(e.target.checked)}
              className="w-4 h-4 accent-teal"
            />
            <label htmlFor="paused" className="text-sm font-mono text-ink cursor-pointer">
              Paused (stop all runs)
            </label>
          </div>

          <button
            type="submit"
            disabled={savingLimits}
            className="px-4 py-1.5 text-sm font-mono bg-teal text-white rounded-sm hover:bg-teal/90 disabled:opacity-50 transition-colors"
          >
            {savingLimits ? "Saving…" : "Save limits"}
          </button>
        </form>
      )}
    </div>
  );
}
