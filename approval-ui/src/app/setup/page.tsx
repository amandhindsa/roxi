"use client"

import { useEffect, useRef, useState } from "react"
import { setupApi, subscriptionsApi, type SetupSession, type Subscription } from "@/lib/api"

const SESSION_KEY = "roxi_setup_session_id"

export default function SetupPage() {
  const [subscriptionId, setSubscriptionId] = useState("")
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
  const [session, setSession] = useState<SetupSession | null>(null)
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Load subscriptions
  useEffect(() => {
    subscriptionsApi.list()
      .then(subs => {
        setSubscriptions(subs)
        if (subs.length > 0) setSubscriptionId(subs[0].id)
      })
      .catch(() => {})
  }, [])

  // Check for existing session in localStorage
  useEffect(() => {
    const savedId = localStorage.getItem(SESSION_KEY)
    if (savedId) {
      setupApi.getSession(savedId)
        .then(s => { setSession(s); setLoading(false) })
        .catch(() => {
          localStorage.removeItem(SESSION_KEY)
          setLoading(false)
        })
    } else {
      setLoading(false)
    }
  }, [])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [session?.messages])

  const handleStart = async () => {
    if (!subscriptionId) return
    setLoading(true)
    setError(null)
    try {
      const s = await setupApi.createSession(subscriptionId)
      setSession(s)
      localStorage.setItem(SESSION_KEY, s.id)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start session")
    } finally {
      setLoading(false)
    }
  }

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!session || !input.trim()) return
    const content = input.trim()
    setInput("")
    setSending(true)
    setError(null)
    try {
      const updated = await setupApi.sendMessage(session.id, content)
      setSession(updated)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Send failed")
    } finally {
      setSending(false)
    }
  }

  const handleReset = () => {
    localStorage.removeItem(SESSION_KEY)
    setSession(null)
    setError(null)
  }

  const formatTime = (iso: string) =>
    new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-ink-soft font-mono text-sm">loading…</p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono font-bold text-lg text-ink">Setup interview</h1>
        {session && (
          <button
            onClick={handleReset}
            className="text-xs font-mono text-ink-soft hover:text-ink border border-rule px-3 py-1.5"
          >
            start over
          </button>
        )}
      </div>

      {error && (
        <div className="border border-amber bg-amber-wash px-4 py-2 mb-4">
          <p className="text-amber font-mono text-sm">{error}</p>
        </div>
      )}

      {!session && (
        <div className="bg-panel border border-rule p-8 max-w-lg">
          <div className="text-xs font-mono text-ink-soft uppercase tracking-wide mb-4">
            Start onboarding interview
          </div>
          <p className="text-sm font-mono text-ink mb-6">
            Roxi will ask you questions to learn about your ideal customer profile, scoring rules, and outreach preferences. This takes about 5 minutes.
          </p>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-mono text-ink-soft block mb-1">Subscription</label>
              <select
                value={subscriptionId}
                onChange={e => setSubscriptionId(e.target.value)}
                className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none"
              >
                {subscriptions.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <button
              onClick={handleStart}
              disabled={!subscriptionId}
              className="w-full py-2.5 bg-teal text-white text-sm font-mono font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              Start setup
            </button>
          </div>
        </div>
      )}

      {session && (
        <div className="flex flex-col h-[600px] bg-panel border border-rule">
          {/* Completion banner */}
          {session.state === "complete" && (
            <div className="border-b border-teal bg-teal-wash px-4 py-3">
              <p className="text-teal font-mono text-sm font-bold">Your configuration is ready</p>
              {session.summary && (
                <p className="text-teal font-mono text-xs mt-1">{session.summary}</p>
              )}
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {session.messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] px-3 py-2 text-sm font-mono ${
                    msg.role === "user"
                      ? "bg-teal text-white"
                      : "bg-ground border border-rule text-ink"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  <p className={`text-xs mt-1 ${msg.role === "user" ? "text-teal-wash" : "text-ink-soft"}`}>
                    {formatTime(msg.created_at)}
                  </p>
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="bg-ground border border-rule px-3 py-2 text-sm font-mono text-ink-soft">
                  thinking…
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          {session.state !== "complete" && (
            <div className="border-t border-rule p-3">
              <form onSubmit={handleSend} className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="Type your response…"
                  disabled={sending}
                  className="flex-1 border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={sending || !input.trim()}
                  className="px-4 py-2 bg-teal text-white text-xs font-mono hover:opacity-90 disabled:opacity-50 transition-opacity"
                >
                  send
                </button>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
