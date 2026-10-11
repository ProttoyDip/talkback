/*
 * Local sample data for ?mock and for the recorded demo (?replay), so the
 * panels can be shown without a backend session. Never used otherwise.
 * It mirrors what the real backend returns (backend/skills, settings_routes).
 */
import type { ActionItem, EventItem, MemoryItem, ReminderItem, SettingsView, SkillItem, TaskItem } from './types'

/** Local "YYYY-MM-DDTHH:MM" for today at a given hour (sample data stays current). */
function today(hour: number, minute = 0, days = 0) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  d.setHours(hour, minute, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(hour)}:${pad(minute)}`
}

let tasks: TaskItem[] = [
  { id: 't1', title: 'Send the slides to Mira', status: 'open', due_at: today(17), priority: 'high', created_at: '2026-10-10T09:00:00Z' },
  { id: 't2', title: 'Book the dentist', status: 'open', due_at: today(12, 0, 2), priority: 'normal', created_at: '2026-10-10T09:05:00Z' },
  { id: 't3', title: 'Water the plants', status: 'open', priority: 'low', created_at: '2026-10-10T09:10:00Z' },
]
let events: EventItem[] = [
  { id: 'e1', title: 'Team standup', starts_at: today(9, 30), ends_at: today(9, 45), kind: 'meeting', status: 'confirmed', created_at: '2026-10-10T09:00:00Z' },
  { id: 'e2', title: 'Focus: slides', starts_at: today(14), ends_at: today(16), kind: 'focus', status: 'confirmed', created_at: '2026-10-10T09:00:00Z' },
]
let reminders: ReminderItem[] = [
  // Always three hours ahead, so sample pages never show it as due or missed.
  { id: 'r1', text: 'Call mom', due_at: new Date(Date.now() + 3 * 3600_000).toISOString(), status: 'scheduled', snooze_count: 0, created_at: '2026-10-10T09:00:00Z' },
]
let mockId = 100

let memories: MemoryItem[] = [
  {
    id: 'm0',
    text: 'Home city is Lisbon',
    kind: 'fact',
    utterance: 'Remember that my home city is Lisbon.',
    created_at: '2026-10-03T08:05:00Z',
  },
  {
    id: 'm1',
    text: 'Prefers Celsius',
    kind: 'preference',
    utterance: 'Remember that I prefer Celsius.',
    created_at: '2026-10-02T09:12:00Z',
  },
  {
    id: 'm3',
    text: 'Likes jazz while working',
    kind: 'preference',
    utterance: '(suggested by TalkBack)',
    created_at: '2026-10-04T10:00:00Z',
    status: 'suggested',
    source: 'assistant_suggestion',
  },
  {
    id: 'm2',
    text: 'Likes short answers',
    kind: 'preference',
    utterance: 'I like short answers.',
    created_at: '2026-10-01T18:40:00Z',
  },
]

let actions: ActionItem[] = [
  {
    id: 'act1',
    tool: 'memory_write',
    status: 'done',
    summary: 'Remembered “Prefers Celsius”',
    created_at: '2026-10-02T09:12:00Z',
    undoable: true,
  },
]

let skills: SkillItem[] = [
  {
    id: 'morning-brief',
    name: 'Morning brief',
    triggers: ['morning brief', 'start my day', 'brief me'],
    allowed_tools: ['weather', 'memory_read'],
    summary: "Today's weather for your city and anything you asked TalkBack to remember for today.",
  },
  {
    id: 'quick-research',
    name: 'Quick research',
    triggers: ['quick research', 'research this', 'look into'],
    allowed_tools: ['web_search'],
    summary: 'One web search, answered in two or three sentences with the source named.',
  },
  {
    id: 'remind-me',
    name: 'Remind me',
    triggers: ['remind me'],
    allowed_tools: ['reminder_set', 'reminder_update', 'memory_read'],
    summary: 'Sets a reminder for a time you name. TalkBack checks the time with you first.',
  },
]

let settings: SettingsView = {
  tools: {
    web_search: { enabled: true, description: 'Searches the web with your question. It sees only that text.' },
    weather: { enabled: true, description: 'Looks up the weather for a place you name.' },
    memory_read: { enabled: true, description: 'Reads what you asked TalkBack to remember.' },
    memory_delete: { enabled: true, description: 'Deletes a saved memory, only after you say yes.' },
  },
  save_recordings: false,
  transcripts_in_logs: false,
  interrupt_sensitivity: 'normal',
  answer_length: 'normal',
  models: {
    voice_model: 'NVIDIA Parakeet speech-to-text + Magpie TTS',
    full_duplex: false,
    planner_model: 'nebius:nemotron-3-nano',
    planner_options: [
      { id: 'nebius:nemotron-3-nano', provider: 'nebius', model: 'Nemotron 3 Nano', nvidia: true, available: true },
      { id: 'openrouter:nemotron', provider: 'openrouter', model: 'Nemotron (OpenRouter)', nvidia: true, available: false },
    ],
    providers: [
      { id: 'nebius', name: 'Nebius Token Factory', role: 'planner', primary: true, enabled: true, configured: true, receives_user_words: true },
      { id: 'openrouter', name: 'OpenRouter', role: 'planner', primary: false, enabled: true, configured: false, receives_user_words: true },
      { id: 'tavily', name: 'Tavily', role: 'search', primary: true, enabled: true, configured: true, receives_user_words: true },
    ],
  },
}

const wait = () => new Promise((resolve) => setTimeout(resolve, 120))

interface SettingsPatch {
  tools?: Record<string, boolean>
  save_recordings?: boolean
  transcripts_in_logs?: boolean
  interrupt_sensitivity?: SettingsView['interrupt_sensitivity']
  answer_length?: SettingsView['answer_length']
  planner_model?: string
  providers?: Record<string, boolean>
}

export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  await wait()
  const [route, query = ''] = path.split('?')
  const id = route.split('/')[3]
  let result: unknown
  if (route.startsWith('/api/tasks')) {
    if (method === 'GET') {
      const status = new URLSearchParams(query).get('status') ?? 'open'
      result = { items: tasks.filter((t) => status === 'all' || t.status === status) }
    } else if (method === 'POST') {
      const task = { id: `t${mockId++}`, status: 'open', priority: 'normal', created_at: new Date().toISOString(), ...(body as object) } as TaskItem
      tasks = [...tasks, task]
      result = task
    } else if (method === 'PATCH') {
      tasks = tasks.map((t) => (t.id === id ? { ...t, ...(body as object) } : t))
      result = tasks.find((t) => t.id === id)
    } else {
      tasks = tasks.filter((t) => t.id !== id)
    }
  } else if (route.startsWith('/api/calendar')) {
    if (method === 'GET') {
      const params = new URLSearchParams(query)
      const [from, to] = [params.get('from') ?? '', params.get('to') ?? '']
      result = { items: events.filter((e) => e.starts_at < to && e.ends_at > from) }
    } else if (method === 'POST') {
      const event = { id: `e${mockId++}`, kind: 'block', status: 'confirmed', created_at: new Date().toISOString(), ...(body as object) } as EventItem
      events = [...events, event].sort((a, b) => a.starts_at.localeCompare(b.starts_at))
      result = event
    } else {
      events = events.filter((e) => e.id !== id)
    }
  } else if (route.startsWith('/api/reminders')) {
    const action = route.split('/')[4]
    if (method === 'GET') {
      result = { items: reminders.filter((r) => r.status === 'scheduled') }
    } else if (method === 'POST' && !action) {
      const reminder = { id: `r${mockId++}`, status: 'scheduled', snooze_count: 0, created_at: new Date().toISOString(), ...(body as object) } as ReminderItem
      reminders = [...reminders, reminder]
      result = reminder
    } else if (method === 'DELETE') {
      reminders = reminders.filter((r) => r.id !== id)
    } else {
      const status = action === 'ack' ? 'acknowledged' : action === 'delivered' ? 'delivered' : 'scheduled'
      reminders = reminders.map((r) => (r.id === id ? { ...r, status } : r))
      result = reminders.find((r) => r.id === id)
    }
  } else if (route === '/api/actions') {
    result = { items: actions }
  } else if (route.startsWith('/api/actions/')) {
    actions = actions.map((a) => (a.id === id ? { ...a, status: 'undone' as const, undoable: false } : a))
    result = actions.find((a) => a.id === id)
  } else if (route.startsWith('/api/memories')) {
    if (method === 'GET') {
      const q = new URLSearchParams(query).get('q')?.toLowerCase() ?? ''
      const history = new URLSearchParams(query).has('history')
      result = {
        items: memories.filter(
          (m) => m.text.toLowerCase().includes(q) && (history || (m.status ?? 'confirmed') !== 'superseded'),
        ),
      }
    } else if (method === 'PATCH') {
      memories = memories.map((m) => (m.id === id ? { ...m, ...(body as object) } : m))
      result = memories.find((m) => m.id === id)
    } else if (id) {
      memories = memories.filter((m) => m.id !== id)
    } else {
      memories = []
    }
  } else if (route === '/api/skills') {
    if (method === 'POST') {
      const skill = { id: `u-${mockId++}`, builtin: false, enabled: true, ...(body as object) } as SkillItem
      skills = [...skills, skill]
      result = skill
    } else {
      result = { items: skills }
    }
  } else if (route.endsWith('/run')) {
    result = { run_id: 'run1' }
  } else if (route.startsWith('/api/skills/')) {
    if (method === 'DELETE') skills = skills.filter((s) => s.id !== id)
    else skills = skills.map((s) => (s.id === id ? { ...s, ...(body as object) } : s))
    result = skills.find((s) => s.id === id)
  } else if (route === '/api/settings') {
    if (method === 'PATCH') {
      const update = body as SettingsPatch
      const tools = { ...settings.tools }
      for (const [name, enabled] of Object.entries(update.tools ?? {})) {
        const key = name as keyof typeof tools
        const current = tools[key]
        if (current) tools[key] = { ...current, enabled }
      }
      settings = {
        ...settings,
        tools,
        save_recordings: update.save_recordings ?? settings.save_recordings,
        transcripts_in_logs: update.transcripts_in_logs ?? settings.transcripts_in_logs,
        interrupt_sensitivity: update.interrupt_sensitivity ?? settings.interrupt_sensitivity,
        answer_length: update.answer_length ?? settings.answer_length,
        models: {
          ...settings.models,
          planner_model: update.planner_model ?? settings.models.planner_model,
          providers: settings.models.providers.map((p) => ({
            ...p,
            enabled: update.providers?.[p.id] ?? p.enabled,
          })),
        },
      }
    }
    result = settings
  }
  return result as T
}
