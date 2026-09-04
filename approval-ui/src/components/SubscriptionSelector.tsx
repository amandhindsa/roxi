"use client"

import { useEffect, useState } from "react"
import { subscriptionsApi, type Subscription } from "@/lib/api"

interface Props {
  value: string
  onChange: (id: string) => void
  className?: string
}

export function SubscriptionSelector({ value, onChange, className = "" }: Props) {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    subscriptionsApi.list()
      .then(data => {
        setSubscriptions(data)
        if (!value && data.length > 0) onChange(data[0].id)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <span className="text-xs font-mono text-ink-soft">loading subscriptions…</span>

  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className={`border border-rule bg-ground px-3 py-1.5 text-sm font-mono text-ink focus:outline-none focus:border-ink ${className}`}
    >
      {subscriptions.map(s => (
        <option key={s.id} value={s.id}>{s.name}</option>
      ))}
    </select>
  )
}
