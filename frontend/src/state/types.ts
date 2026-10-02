/** Conversation states from docs/design.md, section 6. */
export type ConversationState =
  | 'idle'
  | 'listening'
  | 'assistant_speaking'
  | 'overlap'
  | 'interrupted'
  | 'thinking'
  | 'tool'
  | 'confirm'
  | 'muted'
  | 'offline'

export const CONVERSATION_STATES: readonly ConversationState[] = [
  'idle',
  'listening',
  'assistant_speaking',
  'overlap',
  'interrupted',
  'thinking',
  'tool',
  'confirm',
  'muted',
  'offline',
]

export type Speaker = 'user' | 'assistant'

export type ToolName = 'weather' | 'web_search'

export type ToolStatus = 'running' | 'done' | 'failed'

export interface Source {
  title: string
  url: string
}

export interface ToolCall {
  id: string
  name: ToolName
  status: ToolStatus
  sources?: Source[]
}

/**
 * A turn is split into segments so the UI can show what was actually heard.
 * - heard: words that were played to the user
 * - unheard: words cut off by an interruption (shown faded and struck through)
 * - backchannel: a short user sound ("mm-hm") that did not stop TalkBack
 */
export type Segment =
  | { kind: 'heard'; text: string }
  | { kind: 'unheard'; text: string }
  | { kind: 'backchannel'; text: string }

export interface Turn {
  id: string
  speaker: Speaker
  segments: Segment[]
  tools?: ToolCall[]
}

export interface ConfirmRequest {
  callId: string
  summary: string
}

/** Levels are 0..1, one value per 100 ms, oldest first. */
export interface TimelineData {
  windowSeconds: number
  user: number[]
  assistant: number[]
  /** Seconds from the start of the window. */
  interrupts: number[]
}
