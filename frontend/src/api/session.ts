/*
 * Session tokens (SECURITY.md T7). One place asks for them, so the access
 * code for a public demo (SECURITY.md T8) is sent with every request.
 */

const CODE_KEY = 'talkback.accessCode'

/** The server wants an access code, or the one we sent is wrong. */
export class AccessCodeError extends Error {}

export interface SessionToken {
  token: string
  expires_at: number
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

/** POST /api/session. Throws AccessCodeError on 401, Error on anything else. */
export async function requestSession(code = savedAccessCode()): Promise<SessionToken> {
  const response = await fetch('/api/session', {
    method: 'POST',
    headers: code ? { 'X-Access-Code': code } : {},
  })
  if (response.status === 401) throw new AccessCodeError('access code required')
  if (!response.ok) throw new Error(`session request failed: ${response.status}`)
  return (await response.json()) as SessionToken
}
