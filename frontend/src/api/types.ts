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
}
