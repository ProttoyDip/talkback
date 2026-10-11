/*
 * REST types. Mirror the "REST API" section of backend/app/protocol.py and
 * docs/architecture.md 3.2. Change all together, in a "contract" pull request.
 */
import type { ModelRole, ProviderId, ToolName } from '../session/protocol'

export type InterruptSensitivity = 'low' | 'normal' | 'high'
export type AnswerLength = 'short' | 'normal' | 'detailed'

export type MemoryKind = 'preference' | 'fact' | 'reminder'

export interface MemoryItem {
  id: string
  text: string
  kind: MemoryKind
  /** The user's exact words that created it. */
  utterance: string
  created_at: string
  /** suggested: proposed by TalkBack, waiting for an OK. superseded: replaced by a correction. */
  status?: MemoryStatus
  /** Where the words came from: said, typed, edited, or suggested by TalkBack. */
  source?: MemorySource
  updated_at?: string | null
  superseded_by?: string | null
}

export type MemoryStatus = 'confirmed' | 'suggested' | 'superseded' | 'dismissed'
export type MemorySource = 'user_utterance' | 'user_text' | 'user_edit' | 'assistant_suggestion'

/** One change TalkBack made or was asked to make (GET /api/actions). */
export interface ActionItem {
  id: string
  tool: string
  status: 'done' | 'failed' | 'cancelled' | 'declined' | 'expired' | 'undone'
  summary: string
  created_at: string
  finished_at?: string | null
  undoable: boolean
  undone_at?: string | null
}

export interface MemoryUpdate {
  text?: string
  kind?: MemoryKind
  /** Confirm or dismiss a suggestion. */
  status?: 'confirmed' | 'dismissed'
}

export interface SkillItem {
  id: string
  name: string
  triggers: string[]
  allowed_tools: ToolName[]
  /** One plain sentence: what the skill does and what to say. */
  summary?: string
  /** Built-in skills are read-only (but can be copied). */
  builtin?: boolean
  enabled?: boolean
  instructions?: string | null
}

export interface ProviderInfo {
  id: ProviderId
  name: string
  role: ModelRole
  primary: boolean
  enabled: boolean
  configured: boolean
  receives_user_words: boolean
}

export interface ModelOption {
  id: string
  provider: ProviderId
  model: string
  nvidia: boolean
  available: boolean
}

export interface ModelsView {
  voice_model: string
  /** True only for a full-duplex voice model; the cascade engine is turn-based. */
  full_duplex?: boolean
  planner_model: string
  planner_options: ModelOption[]
  providers: ProviderInfo[]
}

export interface ToolSetting {
  enabled: boolean
  description: string
}

export interface SettingsView {
  /** IANA time zone for tasks, calendar and reminders. */
  timezone?: string
  /** Offer to continue an unfinished conversation (plan P7). */
  resume_sessions?: boolean
  /** Keep the last 6 heard turns for that (off by default). */
  keep_recent_turns?: boolean
  tools: Partial<Record<ToolName, ToolSetting>>
  save_recordings: boolean
  transcripts_in_logs: boolean
  interrupt_sensitivity: InterruptSensitivity
  answer_length: AnswerLength
  models: ModelsView
}

export interface SettingsUpdate {
  tools?: Partial<Record<ToolName, boolean>>
  save_recordings?: boolean
  transcripts_in_logs?: boolean
  interrupt_sensitivity?: InterruptSensitivity
  answer_length?: AnswerLength
  planner_model?: string
  providers?: Partial<Record<ProviderId, boolean>>
  timezone?: string
  resume_sessions?: boolean
  keep_recent_turns?: boolean
}

// Tasks, calendar and reminders (plan P5). Times are ISO 8601 with an offset.

export interface TaskItem {
  id: string
  title: string
  notes?: string | null
  status: 'open' | 'done' | 'cancelled'
  due_at?: string | null
  priority: 'low' | 'normal' | 'high'
  created_at: string
  updated_at?: string | null
  completed_at?: string | null
}

export interface EventItem {
  id: string
  title: string
  starts_at: string
  ends_at: string
  kind: 'block' | 'meeting' | 'focus' | 'personal'
  status: 'confirmed' | 'cancelled'
  task_id?: string | null
  created_at: string
  updated_at?: string | null
}

export interface ReminderItem {
  id: string
  text: string
  due_at: string
  status: 'scheduled' | 'delivered' | 'acknowledged' | 'cancelled' | 'missed'
  delivered_at?: string | null
  snooze_count: number
  created_at: string
}

export interface SkillCreate {
  name: string
  triggers: string[]
  allowed_tools: ToolName[]
  instructions: string
  summary?: string | null
}
