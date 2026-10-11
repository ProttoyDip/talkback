import { useId, useState } from 'react'
import { Icon } from './Icon'

/**
 * Type instead of talking (plan P3): for corrections, quiet places, or when
 * the microphone is not available. A typed turn is handled like a spoken one.
 */
export function TextComposer({ onSend, disabled }: { onSend: (text: string) => void; disabled?: boolean }) {
  const [text, setText] = useState('')
  const id = useId()
  const send = () => {
    const value = text.trim()
    if (!value || disabled) return
    onSend(value)
    setText('')
  }

  return (
    <form
      className="flex flex-col gap-1"
      onSubmit={(e) => {
        e.preventDefault()
        send()
      }}
    >
      <label htmlFor={id} className="font-mono text-label uppercase text-text-muted">
        Type instead
      </label>
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="text"
          autoComplete="off"
          maxLength={2000}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          className="min-h-target min-w-0 flex-1 rounded-input border border-field-line bg-chrome px-3 text-body text-text disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          aria-label="Send"
          className="grid size-target shrink-0 place-items-center rounded-pill bg-voice-assistant text-on-accent transition-transform duration-(--dur-instant) active:scale-[0.96] disabled:opacity-60"
        >
          <Icon name="chevron" className="size-4 -rotate-90" />
        </button>
      </div>
    </form>
  )
}
