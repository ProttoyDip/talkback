import { statusDescription, statusLabel } from '../state/status'
import type { ConversationState, ToolName } from '../state/types'

interface StatusBarProps {
  state: ConversationState
  tool?: ToolName
  debug: boolean
  /** Live latency in ms. Undefined until the backend sends `metrics`. */
  latencyMs?: number
}

export function StatusBar({ state, tool, debug, latencyMs }: StatusBarProps) {
  const offline = state === 'offline'

  return (
    <header className="flex items-center justify-between gap-4">
      <p className="font-display text-h2 font-extrabold tracking-tight select-none">
        <span className="text-text">Talk</span>
        <span className="text-voice-assistant">Back</span>
      </p>

      <div className="flex items-center gap-4">
        {debug && (
          <p className="font-mono text-label uppercase text-text-muted">
            Latency{' '}
            <span className="tabular text-data text-text">
              {latencyMs === undefined ? '--' : `${Math.round(latencyMs)} ms`}
            </span>
          </p>
        )}

        <div
          className="flex h-8 items-center gap-2 rounded-pill border border-border px-3"
          role="status"
          aria-live="polite"
        >
          <span
            aria-hidden
            className={[
              'size-2 rounded-pill transition-colors duration-(--dur-fast)',
              offline ? 'bg-danger' : 'bg-voice-assistant',
            ].join(' ')}
          />
          <span aria-hidden className="font-mono text-label font-medium uppercase text-text">
            {statusLabel(state, tool)}
          </span>
          <span className="sr-only">
            {offline ? 'Disconnected. ' : 'Connected. '}
            {statusDescription(state)}
          </span>
        </div>
      </div>
    </header>
  )
}
