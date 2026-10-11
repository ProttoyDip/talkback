/*
 * Session protocol types. Mirrors backend/app/protocol.py and
 * docs/architecture.md section 3. Change all three together, in a
 * "contract" pull request (docs/plan.md section 4).
 */
import type { ConversationState } from '../state/types'

export type ToolName =
  | 'weather'
  | 'web_search'
  | 'memory_read'
  | 'memory_write'
  | 'memory_delete'
  | 'memory_suggest'
  | 'skill_run'
  | 'task_list'
  | 'task_add'
  | 'task_update'
  | 'task_delete'
  | 'calendar_list'
  | 'calendar_add'
  | 'calendar_update'
  | 'calendar_delete'
  | 'reminder_set'
  | 'reminder_update'

/**
 * declined: the user said no or did not answer; cancelled: stopped before it ran;
 * expired: the confirmation ran out. Any final status closes the call's confirm card.
 */
export type ToolCallStatus = 'running' | 'done' | 'failed' | 'declined' | 'cancelled' | 'expired'

export type ToolStatusReason =
  | 'user_declined'
  | 'timeout'
  | 'superseded'
  | 'stopped'
  | 'interrupted'
  | 'session_closed'
  | 'already_done'

import type { ReminderItem } from '../api/types'

export const CLIENT_SAMPLE_RATE = 16_000
export const SERVER_SAMPLE_RATE = 22_050
export const FRAME_SAMPLES = 320 // 20 ms at 16 kHz

// Client -> server

export type ClientMessage =
  | { type: 'session.start'; client_sample_rate: typeof CLIENT_SAMPLE_RATE }
  | { type: 'playback.position'; seq: number; samples_played: number }
  | { type: 'control.mute'; muted: boolean }
  | { type: 'control.stop' }
  | { type: 'tool.confirm'; call_id: string; approved: boolean }
  /** A typed turn, handled like a spoken one; works while muted. */
  | { type: 'text.input'; text: string }

// Server -> client. Optional fields may be missing (missing means null).

export interface Source {
  title: string
  url: string
}

export type ProviderId =
  | 'nebius'
  | 'nvidia'
  | 'openrouter'
  | 'agentrouter'
  | 'nararouter'
  | 'experimentallab'
  | 'tavily'
  | 'perplexity'

export const PROVIDER_NAMES: Record<ProviderId, string> = {
  nebius: 'Nebius',
  nvidia: 'NVIDIA API',
  openrouter: 'OpenRouter',
  agentrouter: 'AgentRouter',
  nararouter: 'Nararouter',
  experimentallab: 'Experiential Labs',
  tavily: 'Tavily',
  perplexity: 'Perplexity',
}

export type ModelRole = 'voice' | 'planner' | 'search'

export type ErrorCode = 'voice_engine_offline' | 'tool_failed' | 'rate_limited' | 'internal'

export type SessionEndReason = 'idle' | 'time_limit' | 'server_shutdown' | 'protocol_error'

export type ServerEvent =
  | { type: 'state'; state: ConversationState; tool?: ToolName }
  | { type: 'audio.chunk'; seq: number; samples: number }
  | { type: 'audio.flush'; reason: 'interrupted' | 'stopped' }
  | {
      type: 'transcript.delta'
      message_id: string
      speaker: 'user' | 'assistant'
      text: string
      final: boolean
      backchannel?: boolean
      /** The user typed this turn (text.input). */
      typed?: boolean
    }
  | { type: 'transcript.trim'; message_id: string; heard_text: string; unheard_text?: string }
  | {
      type: 'tool.status'
      call_id: string
      message_id: string
      name: ToolName
      status: ToolCallStatus
      reason?: ToolStatusReason
      /** The change this call made (Activity panel), and whether it can be undone. */
      action_id?: string
      undoable?: boolean
      sources?: Source[]
    }
  | {
      type: 'tool.confirm_request'
      call_id: string
      summary: string
      message_id?: string
      name?: ToolName
      /** More lines for the card (a day plan). */
      details?: string[]
      expires_in_ms?: number
    }
  | {
      type: 'memory.saved'
      id: string
      text: string
      status?: 'confirmed' | 'suggested'
      replaced_id?: string
      replaced_text?: string
      action_id?: string
    }
  /** Stored data changed by voice: open panels reload. */
  | { type: 'data.changed'; kinds: Array<'memories' | 'actions' | 'tasks' | 'calendar' | 'reminders' | 'skills'> }
  /** A reminder is due now (plan P5). */
  | { type: 'reminder.due'; reminder: ReminderItem }
  | { type: 'metrics'; latency_ms: number }
  | { type: 'error'; code: ErrorCode; message: string; retry_in_ms?: number }
  | { type: 'model.active'; role: ModelRole; provider: ProviderId; model: string; backup: boolean }
  | { type: 'session.end'; reason: SessionEndReason }

const SERVER_EVENT_TYPES = new Set<ServerEvent['type']>([
  'state',
  'audio.chunk',
  'audio.flush',
  'transcript.delta',
  'transcript.trim',
  'tool.status',
  'tool.confirm_request',
  'memory.saved',
  'data.changed',
  'reminder.due',
  'metrics',
  'error',
  'model.active',
  'session.end',
])

/** Parse a text frame. Returns null for anything that is not a known event. */
export function parseServerEvent(text: string): ServerEvent | null {
  try {
    const value: unknown = JSON.parse(text)
    if (
      typeof value === 'object' &&
      value !== null &&
      'type' in value &&
      SERVER_EVENT_TYPES.has((value as { type: ServerEvent['type'] }).type)
    ) {
      return value as ServerEvent
    }
  } catch {
    // fall through
  }
  return null
}
