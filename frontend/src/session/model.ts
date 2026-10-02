/*
 * Conversation model: a pure reducer from session events to what the screen
 * shows. No timers, no I/O, so it is easy to test against the shared fixture.
 */
import type { ConfirmRequest, ConversationState, Segment, ToolCall, Turn } from '../state/types'
import type { ErrorCode, ServerEvent, SessionEndReason, ToolName } from './protocol'

export type Connection = 'connecting' | 'open' | 'reconnecting' | 'closed'

interface Backchannel {
  id: string
  /** Character offset in the assistant text where the user said it. */
  at: number
  text: string
}

interface TurnRecord {
  id: string
  speaker: 'user' | 'assistant'
  text: string
  final: boolean
  /** Set by transcript.trim: the part the user actually heard. */
  heardText?: string
  backchannels: Backchannel[]
  tools: ToolCall[]
}

export interface ConversationModel {
  connection: Connection
  state: ConversationState
  tool?: ToolName
  turns: TurnRecord[]
  confirm?: ConfirmRequest
  error?: { code: ErrorCode; message: string; retryInMs?: number }
  ended?: SessionEndReason
  latencyMs?: number
  /** Times (ms, caller's clock) of audio.flush for interruptions. */
  interrupts: number[]
  /** Last memory saved, for the "Remembered" toast. */
  remembered?: { id: string; text: string }
  /**
   * Where the user started talking over TalkBack: the playing turn and its
   * text length at that moment. A backchannel caption arrives after the
   * sound ends, so this is where the "mm-hm" marker goes.
   */
  overlapStart?: { turnId: string; at: number }
}

export const initialModel: ConversationModel = {
  connection: 'connecting',
  state: 'idle',
  turns: [],
  interrupts: [],
}

export type Action =
  | { kind: 'event'; event: ServerEvent; at: number }
  | { kind: 'connection'; connection: Connection }
  | { kind: 'confirm-answered' }
  | { kind: 'reset' }

function upsertTurn(
  turns: TurnRecord[],
  id: string,
  speaker: TurnRecord['speaker'],
  update: (turn: TurnRecord) => TurnRecord,
): TurnRecord[] {
  const index = turns.findIndex((t) => t.id === id)
  if (index === -1) {
    const fresh: TurnRecord = { id, speaker, text: '', final: false, backchannels: [], tools: [] }
    return [...turns, update(fresh)]
  }
  const next = turns.slice()
  next[index] = update(turns[index])
  return next
}

/** The assistant turn that is playing now, if any (backchannels go there). */
function playingAssistantTurn(turns: TurnRecord[]) {
  const last = turns.at(-1)
  return last?.speaker === 'assistant' && !last.final ? last : undefined
}

function applyEvent(model: ConversationModel, event: ServerEvent, at: number): ConversationModel {
  switch (event.type) {
    case 'state': {
      const playing = playingAssistantTurn(model.turns)
      const overlapStart =
        event.state === 'overlap' && playing
          ? { turnId: playing.id, at: playing.text.length }
          : event.state === 'overlap'
            ? undefined
            : model.overlapStart
      return { ...model, state: event.state, tool: event.tool, overlapStart }
    }

    case 'transcript.delta': {
      if (event.speaker === 'user' && event.backchannel) {
        const host =
          model.turns.find((t) => t.backchannels.some((b) => b.id === event.message_id)) ??
          playingAssistantTurn(model.turns)
        if (host) {
          const at =
            model.overlapStart?.turnId === host.id ? model.overlapStart.at : host.text.length
          return {
            ...model,
            turns: upsertTurn(model.turns, host.id, 'assistant', (turn) => {
              const existing = turn.backchannels.find((b) => b.id === event.message_id)
              const backchannels = existing
                ? turn.backchannels.map((b) => (b.id === event.message_id ? { ...b, text: event.text } : b))
                : [...turn.backchannels, { id: event.message_id, at, text: event.text }]
              return { ...turn, backchannels }
            }),
          }
        }
        // No assistant turn is playing: show it as a normal user turn.
      }
      return {
        ...model,
        turns: upsertTurn(model.turns, event.message_id, event.speaker, (turn) => ({
          ...turn,
          // User deltas carry the full text so far; assistant deltas append.
          text: event.speaker === 'user' ? event.text : turn.text + event.text,
          final: event.final,
        })),
      }
    }

    case 'transcript.trim':
      return {
        ...model,
        turns: upsertTurn(model.turns, event.message_id, 'assistant', (turn) => ({
          ...turn,
          text: event.unheard_text ? `${event.heard_text} ${event.unheard_text}` : event.heard_text,
          heardText: event.heard_text,
          final: true,
        })),
      }

    case 'tool.status': {
      const call: ToolCall = {
        id: event.call_id,
        name: event.name,
        status: event.status,
        sources: event.sources,
      }
      return {
        ...model,
        turns: upsertTurn(model.turns, event.message_id, 'assistant', (turn) => ({
          ...turn,
          tools: turn.tools.some((t) => t.id === call.id)
            ? turn.tools.map((t) => (t.id === call.id ? call : t))
            : [...turn.tools, call],
        })),
      }
    }

    case 'tool.confirm_request':
      return { ...model, confirm: { callId: event.call_id, summary: event.summary } }

    case 'audio.flush':
      return event.reason === 'interrupted'
        ? { ...model, interrupts: [...model.interrupts, at] }
        : model

    case 'memory.saved':
      return { ...model, remembered: { id: event.id, text: event.text } }

    case 'metrics':
      return { ...model, latencyMs: event.latency_ms }

    case 'error':
      return {
        ...model,
        error: { code: event.code, message: event.message, retryInMs: event.retry_in_ms },
      }

    case 'session.end':
      return { ...model, ended: event.reason }

    case 'audio.chunk':
      return model // audio is handled by the playback layer
  }
}

export function reduce(model: ConversationModel, action: Action): ConversationModel {
  switch (action.kind) {
    case 'event':
      return applyEvent(model, action.event, action.at)
    case 'connection':
      return {
        ...model,
        connection: action.connection,
        // A new connection clears connection-level problems; the transcript stays.
        ...(action.connection === 'open' ? { error: undefined, ended: undefined } : {}),
      }
    case 'confirm-answered':
      return { ...model, confirm: undefined }
    case 'reset':
      return initialModel
  }
}

/** Build the transcript the components render. */
export function toTurns(model: ConversationModel): Turn[] {
  return model.turns
    .filter((turn) => turn.text || turn.tools.length || turn.backchannels.length)
    .map((turn) => ({
      id: turn.id,
      speaker: turn.speaker,
      tools: turn.tools.length ? turn.tools : undefined,
      segments: turn.speaker === 'user' ? [{ kind: 'heard', text: turn.text }] : assistantSegments(turn),
    }))
}

function assistantSegments(turn: TurnRecord): Segment[] {
  const heard = turn.heardText ?? turn.text
  const unheard = turn.heardText === undefined ? '' : turn.text.slice(heard.length)
  const segments: Segment[] = []
  let cursor = 0
  for (const bc of [...turn.backchannels].sort((a, b) => a.at - b.at)) {
    const at = Math.min(bc.at, heard.length)
    const before = heard.slice(cursor, at).trim()
    if (before) segments.push({ kind: 'heard', text: before })
    segments.push({ kind: 'backchannel', text: bc.text })
    cursor = at
  }
  const rest = heard.slice(cursor).trim()
  if (rest) segments.push({ kind: 'heard', text: rest })
  if (unheard.trim()) segments.push({ kind: 'unheard', text: unheard.trim() })
  return segments
}
