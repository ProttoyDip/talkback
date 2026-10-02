import { MotionConfig } from 'motion/react'
import { LiveConversation } from './screens/LiveConversation'
import { PreviewConversation } from './screens/PreviewConversation'
import { CONVERSATION_STATES, type ConversationState } from './state/types'

/*
 * The URL picks the mode:
 *   (default)   live session with the backend (via the Vite proxy in dev)
 *   ?replay     plays docs/fixtures/demo_session.jsonl, no backend needed
 *               (&speed=4 plays it 4x faster; used by the end-to-end tests)
 *   ?state=...  static design preview of one state (idle, listening, overlap,
 *               interrupted, tool, confirm, muted, offline, ...)
 *   ?debug=1    shows the latency readout (architecture.md 11)
 */
function readMode() {
  const params = new URLSearchParams(window.location.search)
  const debug = params.get('debug') === '1'
  const requested = params.get('state') as ConversationState | null
  if (requested && CONVERSATION_STATES.includes(requested)) {
    return { kind: 'preview' as const, state: requested, debug }
  }
  const speed = Number(params.get('speed') ?? 1)
  return {
    kind: params.has('replay') ? ('replay' as const) : ('live' as const),
    debug,
    replaySpeed: Number.isFinite(speed) && speed > 0 ? Math.min(speed, 20) : 1,
  }
}

export default function App() {
  const mode = readMode()
  return (
    <MotionConfig reducedMotion="user">
      {mode.kind === 'preview' ? (
        <PreviewConversation state={mode.state} debug={mode.debug} />
      ) : (
        <LiveConversation mode={mode.kind} debug={mode.debug} replaySpeed={mode.replaySpeed} />
      )}
    </MotionConfig>
  )
}
