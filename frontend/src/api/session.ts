/*
 * Session tokens (SECURITY.md T7). One place asks for them, so the access
 * code for a public demo (SECURITY.md T8) is sent with every request.
 */

const CODE_KEY = 'talkback.accessCode'

import { accessToken } from './auth'

/** The server wants an access code, or the one we sent is wrong. */
export class AccessCodeError extends Error {}

/** Accounts are on and this browser is not signed in (or its sign-in expired). */
export class SignInRequiredError extends Error {}

/** GET /api/auth-config: how this server signs people in. */
export interface AuthConfig {
  mode: 'off' | 'optional' | 'required'
  supabase_url?: string | null
  publishable_key?: string | null
  access_code: boolean
}

/** Who the session belongs to; "local" when the server has no accounts. */
export interface SessionUser {
  id: string
  email?: string | null
  anonymous: boolean
}

export interface SessionToken {
  token: string
  expires_at: number
  user?: SessionUser | null
}

export function savedAccessCode(): string {
  try {
    return localStorage.getItem(CODE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function saveAccessCode(code: string) {
  try {
    if (code) localStorage.setItem(CODE_KEY, code)
    else localStorage.removeItem(CODE_KEY)
  } catch {
    // Private mode: the code lasts until the page closes.
  }
}

/**
 * POST /api/session. Throws AccessCodeError or SignInRequiredError on 401,
 * Error on anything else. Sends the Supabase access token when signed in.
 */
export async function requestSession(code = savedAccessCode()): Promise<SessionToken> {
  const headers: Record<string, string> = {}
  if (code) headers['X-Access-Code'] = code
  const token = await accessToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch('/api/session', { method: 'POST', headers })
  if (response.status === 401) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined)
    if (detail === 'sign_in_required') throw new SignInRequiredError('sign in required')
    throw new AccessCodeError('access code required')
  }
  if (!response.ok) throw new Error(`session request failed: ${response.status}`)
  return (await response.json()) as SessionToken
}
