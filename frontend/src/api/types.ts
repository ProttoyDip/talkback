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
}

export interface MemoryUpdate {
  text?: string
  kind?: MemoryKind
}

export interface SkillItem {
  id: string
  name: string
  triggers: string[]
  allowed_tools: ToolName[]
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
