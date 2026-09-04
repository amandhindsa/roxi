"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { createBrowserClient } from "@/lib/supabase"

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    const client = createBrowserClient()
    const { error } = await client.auth.signInWithPassword({ email, password })
    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      router.push("/")
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-ground">
      <div className="bg-panel border border-rule p-8 w-full max-w-sm">
        <div className="mb-8">
          <span className="font-mono text-sm font-medium tracking-tight">Roxi</span>
          <h1 className="text-xl font-medium mt-2">Sign in</h1>
          <p className="text-ink-soft text-sm font-mono mt-1">Lead approval dashboard</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-ink-soft mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
              placeholder="you@company.com"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-ink-soft mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              className="w-full border border-rule bg-ground px-3 py-2 text-sm font-mono focus:outline-none focus:border-ink"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="text-sm font-mono text-amber bg-amber-wash border border-amber px-3 py-2">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-teal text-white text-sm font-mono font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  )
}
