"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { createBrowserClient } from "@/lib/supabase"

const NAV_LINKS = [
  { href: "/", label: "leads" },
  { href: "/history", label: "history" },
  { href: "/runs", label: "runs" },
  { href: "/rules", label: "rules" },
  { href: "/sources", label: "sources" },
  { href: "/results", label: "results" },
  { href: "/settings", label: "settings" },
]

export function NavBar() {
  const pathname = usePathname()
  const router = useRouter()
  const [email, setEmail] = useState<string | null>(null)
  const showOperator = process.env.NEXT_PUBLIC_SHOW_OPERATOR === "true"

  useEffect(() => {
    const client = createBrowserClient()
    client.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? null)
    })
  }, [])

  const handleLogout = async () => {
    const client = createBrowserClient()
    await client.auth.signOut()
    router.push("/login")
  }

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/"
    return pathname.startsWith(href)
  }

  return (
    <header className="border-b-2 border-ink bg-panel">
      <div className="max-w-5xl mx-auto px-4 flex items-center gap-6 h-12">
        <span className="font-mono text-sm font-bold tracking-tight text-ink mr-2">Roxi</span>
        <nav className="flex items-center gap-1 flex-1">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={`px-2 py-1 text-xs font-mono transition-colors ${
                isActive(href)
                  ? "text-teal font-bold border-b-2 border-teal"
                  : "text-ink-soft hover:text-ink"
              }`}
            >
              {label}
            </Link>
          ))}
          {showOperator && (
            <Link
              href="/operator"
              className={`px-2 py-1 text-xs font-mono transition-colors ${
                isActive("/operator")
                  ? "text-teal font-bold border-b-2 border-teal"
                  : "text-ink-soft hover:text-ink"
              }`}
            >
              operator
            </Link>
          )}
        </nav>
        <div className="flex items-center gap-3">
          {email && (
            <span className="text-xs font-mono text-ink-soft truncate max-w-[180px]">{email}</span>
          )}
          <button
            onClick={handleLogout}
            className="text-xs font-mono text-ink-soft hover:text-ink border border-rule px-2 py-1 transition-colors"
          >
            logout
          </button>
        </div>
      </div>
    </header>
  )
}
