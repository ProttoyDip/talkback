/*
 * REST client for the memory, skills and settings panels. Every route needs
 * the short-lived session token (SECURITY.md T7), fetched once and renewed
 * a minute before it expires. Add ?mock to the URL to use local sample data
 * while a backend route does not exist yet (mock.ts).
 */
import { mockRequest } from './mock'
import { requestSession } from './session'
import type { MemoryItem, MemoryUpdate, SettingsUpdate, SettingsView, SkillItem } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const USE_MOCK = new URLSearchParams(window.location.search).has('mock')

let cached: { token: string; expiresAt: number } | undefined

/** The live conversation shares its token, so REST calls (Run a skill) act on that session. */
export function rememberSessionToken(token: string, expiresAt: number) {
  cached = { token, expiresAt }
}

async function token(): Promise<string> {
  if (cached && cached.expiresAt * 1000 - Date.now() > 60_000) return cached.token
  let body: { token: string; expires_at: number }
  try {
    body = await requestSession()
  } catch {
    throw new ApiError(0, 'Could not reach the server.')
  }
  cached = { token: body.token, expiresAt: body.expires_at }
  return body.token
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (USE_MOCK) return mockRequest<T>(method, path, body)
  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers: {
        Authorization: `Bearer ${await token()}`,
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, 'Could not reach the server.')
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 404 ? 'The server does not offer this yet.' : 'The server could not do that.',
    )
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const api = {
  listMemories: (q: string) =>
    request<{ items: MemoryItem[] }>('GET', `/api/memories?q=${encodeURIComponent(q)}`).then((r) => r.items),
  editMemory: (id: string, update: MemoryUpdate) =>
    request<MemoryItem>('PATCH', `/api/memories/${encodeURIComponent(id)}`, update),
  deleteMemory: (id: string) => request<void>('DELETE', `/api/memories/${encodeURIComponent(id)}`),
  forgetEverything: () => request<void>('DELETE', '/api/memories'),
  listSkills: () => request<{ items: SkillItem[] }>('GET', '/api/skills').then((r) => r.items),
  runSkill: (id: string) => request<{ run_id: string }>('POST', `/api/skills/${encodeURIComponent(id)}/run`),
  getSettings: () => request<SettingsView>('GET', '/api/settings'),
  updateSettings: (update: SettingsUpdate) => request<SettingsView>('PATCH', '/api/settings', update),
}
