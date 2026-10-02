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
  | 'skill_run'

export const CLIENT_SAMPLE_RATE = 16_000
export const SERVER_SAMPLE_RATE = 22_050
export const FRAME_SAMPLES = 320 // 20 ms at 16 kHz

// Client -> server

export type ClientMessage =
  | { type: 'session.start'; client_sample_rate: typeof CLIENT_SAMPLE_RATE }
  | { type: 'playback.position'; seq: number; samples_played: number }
  | { type: 'control.mute'; muted: boolean }
  | { type: 'tool.confirm'; call_id: string; approved: boolean }

// Server -> client. Optional fields may be missing (missing means null).

export interface Source {
  title: string
  url: string
}

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
    }
  | { type: 'transcript.trim'; message_id: string; heard_text: string; unheard_text?: string }
  | {
      type: 'tool.status'
      call_id: string
      message_id: string
      name: ToolName
      status: 'running' | 'done' | 'failed'
      sources?: Source[]
    }
  | { type: 'tool.confirm_request'; call_id: string; summary: string; expires_in_ms?: number }
  | { type: 'memory.saved'; id: string; text: string }
  | { type: 'metrics'; latency_ms: number }
  | { type: 'error'; code: ErrorCode; message: string; retry_in_ms?: number }
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
  'metrics',
  'error',
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
