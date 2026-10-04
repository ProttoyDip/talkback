import { useState } from 'react'
import {
  placeholderConfirm,
  placeholderInputLevel,
  placeholderTimeline,
  placeholderToolTurn,
  placeholderTurns,
} from '../state/placeholder'
import type { ConversationState, TimelineData } from '../state/types'
import { ConversationScreen, type ConversationView } from './ConversationScreen'

const QUIET: TimelineData = {
  windowSeconds: placeholderTimeline.windowSeconds,
  user: placeholderTimeline.user.map(() => 0),
  assistant: placeholderTimeline.assistant.map(() => 0),
  interrupts: [],
}

/** Design review: shows one state with static example data (`?state=`). */
export function PreviewConversation({ state: requested, debug }: { state: ConversationState; debug: boolean }) {
  const [muted, setMuted] = useState(requested === 'muted')
  const [confirmOpen, setConfirmOpen] = useState(requested === 'confirm')

  const offline = requested === 'offline'
  const state: ConversationState = offline
    ? 'offline'
    : muted
      ? 'muted'
      : requested === 'muted'
        ? 'idle'
        : requested === 'confirm' && !confirmOpen
          ? 'assistant_speaking'
          : requested

  const view: ConversationView = {
    state,
    tool: state === 'tool' ? 'weather' : undefined,
    turns:
      state === 'idle'
        ? []
        : state === 'tool' || state === 'thinking'
          ? [...placeholderTurns, placeholderToolTurn]
          : placeholderTurns,
    confirm: confirmOpen && !offline ? placeholderConfirm : undefined,
    banner: offline
      ? {
          tone: 'danger',
          message: "The voice engine isn't reachable. Retrying in 5 seconds…",
          action: { label: 'Retry now', onClick: () => {} },
        }
      : undefined,
    timeline: state === 'idle' || offline ? QUIET : placeholderTimeline,
    inputLevel: state === 'listening' || state === 'overlap' ? placeholderInputLevel : 0,
    micMode: muted ? 'muted' : 'live',
    micDisabled: offline,
  }

  return (
    <ConversationScreen
      view={view}
      debug={debug}
      onToggleMute={() => setMuted((m) => !m)}
      onAnswerConfirm={() => setConfirmOpen(false)}
      onStop={() => {}}
    />
  )
}
