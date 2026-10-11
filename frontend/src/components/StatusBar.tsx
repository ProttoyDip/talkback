import { statusDescription, statusLabel } from '../state/status'
import { Icon } from './Icon'
import type { ConversationState, ToolName } from '../state/types'

interface StatusBarProps {
  state: ConversationState
  tool?: ToolName
  debug: boolean
  /** Live latency in ms. Undefined until the backend sends `metrics`. */
  latencyMs?: number
  /** Set while a backup provider answers (plan.md 8.2): "Planner: model via provider". */
  backup?: string
  /** The recorded demo is playing, not a live conversation. */
  replay?: boolean
  /** The live session is open (not just ready to start). */
  connected?: boolean
  /** Saves the transcript as a Markdown file; missing until there is one. */
  onSave?: () => void
  /** Downloads the opt-in recording of your voice; missing unless it is on. */
  onSaveRecording?: () => void
}

export function StatusBar({
  state,
  tool,
  debug,
  latencyMs,
  backup,
  replay,
  connected,
  onSave,
  onSaveRecording,
}: StatusBarProps) {
  const offline = state === 'offline'
  const connection = replay
    ? "Playing a recorded demo. TalkBack isn't listening. "
    : offline
      ? 'Disconnected. '
      : connected
        ? 'Connected. '
        : ''

  return (
    <header className="flex items-center justify-between gap-4">
      <p className="font-display text-h2 font-extrabold tracking-tight select-none">
        <span className="text-text">Talk</span>
        <span className="text-voice-assistant">Back</span>
      </p>

      <div className="flex items-center gap-3 sm:gap-4">
        {replay && (
          <p className="flex h-8 items-center rounded-pill border border-voice-user px-3 font-mono text-label font-medium uppercase text-voice-user">
            Recorded demo
          </p>
        )}
        {backup && (
          <p
            className="flex h-8 items-center rounded-pill border border-warning px-3 font-mono text-label font-medium uppercase text-warning"
            title={backup}
          >
            Backup model
            <span className="sr-only">: {backup}</span>
          </p>
        )}
        {debug && (
          <p className="font-mono text-label uppercase text-text-muted">
            Latency{' '}
            <span className="tabular text-data text-text">
              {latencyMs === undefined ? '--' : `${Math.round(latencyMs)} ms`}
            </span>
          </p>
        )}

        {onSaveRecording && (
          <button
            type="button"
            onClick={onSaveRecording}
            aria-label="Save recording of your voice"
            title="Save recording of your voice"
            className="grid size-target place-items-center rounded-pill border border-field-line bg-chrome text-text-muted transition-colors duration-(--dur-fast) hover:text-text active:scale-[0.96]"
          >
            <Icon name="mic" className="size-4" />
          </button>
        )}
        {onSave && (
          <button
            type="button"
            onClick={onSave}
            aria-label="Save transcript"
            title="Save transcript"
            className="grid size-target place-items-center rounded-pill border border-field-line bg-chrome text-text-muted transition-colors duration-(--dur-fast) hover:text-text active:scale-[0.96]"
          >
            <Icon name="download" className="size-4" />
          </button>
        )}
        <div
          className="flex h-8 items-center gap-2 rounded-pill border border-field-line bg-chrome px-3"
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
            {connection}
            {statusDescription(state)}
          </span>
        </div>
      </div>
    </header>
  )
}
