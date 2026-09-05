import { createServerClient as _createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

// For server components / route handlers only
export async function createSupabaseServerClient() {
  const cookieStore = await cookies()
  return _createServerClient(url, anon, {
    cookies: {
      getAll() { return cookieStore.getAll() },
      setAll(cookiesToSet: { name: string; value: string; options: import('@supabase/ssr').CookieOptions }[]) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        } catch {
          // In Server Components cookies() is read-only — ignore
        }
      }
    }
  })
}
