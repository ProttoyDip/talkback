import { MotionConfig } from 'motion/react'
import { LiveConversation } from './screens/LiveConversation'
import { PreviewConversation } from './screens/PreviewConversation'
import { CONVERSATION_STATES, type ConversationState } from './state/types'

/*
 * The URL picks the mode:
 *   (default)   live session with the backend (via the Vite proxy in dev)
 *   ?replay     plays docs/fixtures/demo_session.jsonl, no backend needed
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
  return { kind: params.has('replay') ? ('replay' as const) : ('live' as const), debug }
}

export default function App() {
  const mode = readMode()
  return (
    <MotionConfig reducedMotion="user">
      {mode.kind === 'preview' ? (
        <PreviewConversation state={mode.state} debug={mode.debug} />
      ) : (
        <LiveConversation mode={mode.kind} debug={mode.debug} />
      )}
    </MotionConfig>
  )
}
