/*
 * Accounts (Supabase Auth). The server says whether they are on
 * (GET /api/auth-config); when they are, this browser signs in with an email
 * link or as a guest, and only POST /api/session ever sees the Supabase
 * access token. The Supabase client loads only when accounts are on.
 */
import type { SupabaseClient } from '@supabase/supabase-js'
import type { AuthConfig } from './session'

let config: Promise<AuthConfig> | undefined
let client: Promise<SupabaseClient | null> | undefined

const OFF: AuthConfig = { mode: 'off', access_code: false }

export function authConfig(): Promise<AuthConfig> {
  config ??= fetch('/api/auth-config')
    .then((response) => (response.ok ? (response.json() as Promise<AuthConfig>) : OFF))
    .catch(() => OFF)
  return config
}

async function supabase(): Promise<SupabaseClient | null> {
  client ??= authConfig().then(async (cfg) => {
    if (cfg.mode === 'off' || !cfg.supabase_url || !cfg.publishable_key) return null
    const { createClient } = await import('@supabase/supabase-js')
    return createClient(cfg.supabase_url, cfg.publishable_key, {
      auth: { flowType: 'pkce', persistSession: true, detectSessionInUrl: true },
    })
  })
  return client
}

/** The signed-in user's access token, for POST /api/session only. */
export async function accessToken(): Promise<string | undefined> {
  const sb = await supabase()
  if (!sb) return undefined
  const { data } = await sb.auth.getSession()
  return data.session?.access_token
}

export interface Account {
  email?: string
  guest: boolean
}

export async function currentAccount(): Promise<Account | null> {
  const sb = await supabase()
  if (!sb) return null
  const { data } = await sb.auth.getSession()
  const user = data.session?.user
  return user ? { email: user.email ?? undefined, guest: user.is_anonymous ?? false } : null
}

/** Email a sign-in link that comes back to this page. */
export async function sendSignInLink(email: string): Promise<void> {
  const sb = await supabase()
  if (!sb) throw new Error('accounts are off')
  const { error } = await sb.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: `${window.location.origin}${window.location.pathname}` },
  })
  if (error) throw error
}

/** A guest account for this browser (the server still asks for the access code). */
export async function signInAsGuest(): Promise<void> {
  const sb = await supabase()
  if (!sb) throw new Error('accounts are off')
  const { error } = await sb.auth.signInAnonymously()
  if (error) throw error
}

export async function signOut(): Promise<void> {
  const sb = await supabase()
  await sb?.auth.signOut()
}
