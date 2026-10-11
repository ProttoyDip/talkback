/*
 * Local sample data for ?mock and for the recorded demo (?replay), so the
 * panels can be shown without a backend session. Never used otherwise.
 * It mirrors what the real backend returns (backend/skills, settings_routes).
 */
import type { MemoryItem, SettingsView, SkillItem } from './types'

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
    id: 'm2',
    text: 'Likes short answers',
    kind: 'preference',
    utterance: 'I like short answers.',
    created_at: '2026-10-01T18:40:00Z',
  },
]

const skills: SkillItem[] = [
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
    allowed_tools: ['memory_read'],
    summary: 'Saves a note that TalkBack reads back when you ask. It does not send alerts yet.',
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
  if (route.startsWith('/api/memories')) {
    if (method === 'GET') {
      const q = new URLSearchParams(query).get('q')?.toLowerCase() ?? ''
      result = { items: memories.filter((m) => m.text.toLowerCase().includes(q)) }
    } else if (method === 'PATCH') {
      memories = memories.map((m) => (m.id === id ? { ...m, ...(body as object) } : m))
      result = memories.find((m) => m.id === id)
    } else if (id) {
      memories = memories.filter((m) => m.id !== id)
    } else {
      memories = []
    }
  } else if (route === '/api/skills') {
    result = { items: skills }
  } else if (route.startsWith('/api/skills/')) {
    result = { run_id: 'run1' }
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
