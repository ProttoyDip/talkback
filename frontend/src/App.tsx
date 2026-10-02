import { MotionConfig } from 'motion/react'
import { ConversationScreen } from './screens/ConversationScreen'
import { CONVERSATION_STATES, type ConversationState } from './state/types'

/*
 * Until audio and the session exist, the URL picks what to preview:
 *   ?state=listening | overlap | interrupted | tool | confirm | muted | offline | idle …
 *   ?debug=1  shows the latency readout (architecture.md 11)
 */
function readPreview() {
  const params = new URLSearchParams(window.location.search)
  const requested = params.get('state') as ConversationState | null
  const state: ConversationState =
    requested && CONVERSATION_STATES.includes(requested) ? requested : 'assistant_speaking'
  return { state, debug: params.get('debug') === '1' }
}

export default function App() {
  const { state, debug } = readPreview()
  return (
    <MotionConfig reducedMotion="user">
      <ConversationScreen initialState={state} debug={debug} />
    </MotionConfig>
  )
}
