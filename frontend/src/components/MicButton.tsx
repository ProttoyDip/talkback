import { Icon } from './Icon'

export type MicMode = 'off' | 'live' | 'muted'

interface MicButtonProps {
  mode: MicMode
  /** 0..1. Drives the ring while the user is speaking. Static for now. */
  level: number
  disabled?: boolean
  onToggle: () => void
}

/**
 * 72 px round mic control (design.md 5.2). The outer ring scales with the
 * input level; it does not loop on its own. `Space` toggles mute (wired in
 * the screen so it works without focus on the button).
 */
export function MicButton({ mode, level, disabled, onToggle }: MicButtonProps) {
  const muted = mode === 'muted'
  const live = mode === 'live' && !disabled
  const ringScale = 1 + Math.min(1, Math.max(0, level)) * 0.22

  const label = disabled
    ? 'Microphone unavailable while offline'
    : muted
      ? 'Unmute microphone'
      : mode === 'off'
        ? 'Turn on microphone'
        : 'Mute microphone'

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative grid size-mic place-items-center">
        {live && (
          <span
            aria-hidden
            className="absolute inset-0 rounded-pill border-2 border-voice-assistant opacity-40 transition-transform duration-(--dur-fast) ease-enter motion-reduce:transition-none"
            style={{ transform: `scale(${ringScale})` }}
          />
        )}
        <button
          type="button"
          onClick={onToggle}
          disabled={disabled}
          aria-pressed={muted}
          aria-label={label}
          className={[
            'relative grid size-mic place-items-center rounded-pill border-2 transition-[transform,background-color,border-color,color] duration-(--dur-instant) active:scale-95',
            'disabled:cursor-not-allowed disabled:border-border disabled:bg-surface disabled:text-text-subtle',
            muted
              ? 'border-border bg-surface-raised text-text-muted hover:text-text'
              : mode === 'off'
                ? 'border-border bg-surface text-text hover:border-text-subtle'
                : 'border-voice-assistant bg-voice-assistant text-on-accent',
          ].join(' ')}
        >
          <Icon name={muted ? 'micOff' : 'mic'} className="size-8" />
        </button>
      </div>
      <p aria-hidden className="hidden font-mono text-label uppercase text-text-muted lg:block">
        {disabled ? 'Offline' : muted ? 'Muted · Space to unmute' : 'Space to mute'}
      </p>
    </div>
  )
}
