import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Roxi",
  description: "GTM automation — lead approval and control dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans">
        <header className="border-b-2 border-ink px-6 py-3 flex items-center gap-6">
          <span className="font-mono text-sm font-medium tracking-tight select-none">Roxi</span>
          <nav className="flex gap-4 text-sm font-mono text-ink-soft">
            <Link href="/" className="hover:text-ink transition-colors">leads</Link>
            <Link href="/dashboard" className="hover:text-ink transition-colors">dashboard</Link>
          </nav>
        </header>
        <main className="max-w-5xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
