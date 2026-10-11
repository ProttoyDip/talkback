/*
 * REST client for the memory, skills and settings panels. Every route needs
 * the short-lived session token (SECURITY.md T7), fetched once and renewed
 * a minute before it expires. Add ?mock to the URL to use local sample data
 * while a backend route does not exist yet (mock.ts).
 */
import { mockRequest } from './mock'
import { requestSession } from './session'
import type {
  ActionItem,
  EventItem,
  MemoryItem,
  MemoryUpdate,
  ReminderItem,
  SettingsUpdate,
  SettingsView,
  SkillCreate,
  SkillItem,
  TaskItem,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// The recorded demo (?replay) has no session of its own, so its panels show sample data too.
const params = new URLSearchParams(window.location.search)
/** Stored data changed from this page (an undo): open panels reload. */
export const DATA_CHANGED = 'talkback:data-changed'
function dataChanged() {
  window.dispatchEvent(new Event(DATA_CHANGED))
}

export const USE_MOCK = params.has('mock') || params.has('replay')

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
    // A 409 explains itself ("It changed since, so it can't be undone").
    const detail =
      response.status === 409
        ? await response
            .json()
            .then((body: { detail?: unknown }) => (typeof body.detail === 'string' ? `${body.detail}.` : undefined))
            .catch(() => undefined)
        : undefined
    throw new ApiError(
      response.status,
      detail ??
        (response.status === 404 ? 'The server does not offer this yet.' : 'The server could not do that.'),
    )
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const api = {
  listMemories: (q: string, history = false) =>
    request<{ items: MemoryItem[] }>(
      'GET',
      `/api/memories?q=${encodeURIComponent(q)}${history ? '&history=1' : ''}`,
    ).then((r) => r.items),
  editMemory: (id: string, update: MemoryUpdate) =>
    request<MemoryItem>('PATCH', `/api/memories/${encodeURIComponent(id)}`, update),
  deleteMemory: (id: string) => request<void>('DELETE', `/api/memories/${encodeURIComponent(id)}`),
  forgetEverything: () => request<void>('DELETE', '/api/memories'),
  listActions: () => request<{ items: ActionItem[] }>('GET', '/api/actions?limit=50').then((r) => r.items),
  undoAction: (id: string) =>
    request<ActionItem>('POST', `/api/actions/${encodeURIComponent(id)}/undo`).then((item) => {
      dataChanged() // open panels reload, as after a change by voice
      return item
    }),
  listSkills: () => request<{ items: SkillItem[] }>('GET', '/api/skills').then((r) => r.items),
  runSkill: (id: string) => request<{ run_id: string }>('POST', `/api/skills/${encodeURIComponent(id)}/run`),
  getSettings: () => request<SettingsView>('GET', '/api/settings'),
  // Your own skills (plan P5)
  createSkill: (skill: SkillCreate) => request<SkillItem>('POST', '/api/skills', skill),
  updateSkill: (id: string, update: Partial<SkillCreate> & { enabled?: boolean }) =>
    request<SkillItem>('PATCH', `/api/skills/${encodeURIComponent(id)}`, update),
  deleteSkill: (id: string) => request<void>('DELETE', `/api/skills/${encodeURIComponent(id)}`),
  // Tasks, calendar, reminders (plan P5). Times are local: "2026-10-12T15:00".
  listTasks: (status: 'open' | 'done' | 'all' = 'open') =>
    request<{ items: TaskItem[] }>('GET', `/api/tasks?status=${status}`).then((r) => r.items),
  addTask: (task: { title: string; due_at?: string; priority?: TaskItem['priority'] }) =>
    request<TaskItem>('POST', '/api/tasks', task),
  updateTask: (id: string, update: Partial<Pick<TaskItem, 'title' | 'status' | 'due_at' | 'priority'>>) =>
    request<TaskItem>('PATCH', `/api/tasks/${encodeURIComponent(id)}`, update),
  deleteTask: (id: string) => request<void>('DELETE', `/api/tasks/${encodeURIComponent(id)}`),
  listEvents: (from: string, to: string) =>
    request<{ items: EventItem[] }>(
      'GET',
      `/api/calendar?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ).then((r) => r.items),
  addEvent: (event: { title: string; starts_at: string; ends_at: string; kind?: EventItem['kind'] }) =>
    request<EventItem>('POST', '/api/calendar', event),
  deleteEvent: (id: string) => request<void>('DELETE', `/api/calendar/${encodeURIComponent(id)}`),
  listReminders: (dueBefore?: string) =>
    request<{ items: ReminderItem[] }>(
      'GET',
      `/api/reminders${dueBefore ? `?due_before=${encodeURIComponent(dueBefore)}` : ''}`,
    ).then((r) => r.items),
  setReminder: (reminder: { text: string; due_at: string }) => request<ReminderItem>('POST', '/api/reminders', reminder),
  reminderDelivered: (id: string) =>
    request<ReminderItem>('POST', `/api/reminders/${encodeURIComponent(id)}/delivered`),
  reminderDone: (id: string) => request<ReminderItem>('POST', `/api/reminders/${encodeURIComponent(id)}/ack`),
  snoozeReminder: (id: string, minutes: number) =>
    request<ReminderItem>('POST', `/api/reminders/${encodeURIComponent(id)}/snooze`, { minutes }),
  applyPlan: (id: string, items?: number[]) =>
    request<{ proposal_id: string; status: 'accepted' | 'partially_applied'; applied: number[]; action_id?: string | null }>(
      'POST',
      `/api/plans/${encodeURIComponent(id)}/apply`,
      { items },
    ).then((result) => {
      dataChanged()
      return result
    }),
  rejectPlan: (id: string) => request<void>('POST', `/api/plans/${encodeURIComponent(id)}/reject`),
  choosePlanItems: (id: string, items: number[]) =>
    request<void>('POST', `/api/plans/${encodeURIComponent(id)}/choose`, { items }),
  cancelReminder: (id: string) => request<void>('DELETE', `/api/reminders/${encodeURIComponent(id)}`),
  updateSettings: (update: SettingsUpdate) => request<SettingsView>('PATCH', '/api/settings', update),
}
