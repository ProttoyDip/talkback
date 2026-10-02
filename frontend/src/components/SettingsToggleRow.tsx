import { useId } from 'react'

interface SettingsToggleRowProps {
  label: string
  description?: string
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
}

/** Label, description and a switch (design.md 11). A real checkbox underneath. */
export function SettingsToggleRow({ label, description, checked, onChange, disabled }: SettingsToggleRowProps) {
  const id = useId()
  return (
    <div className="flex min-h-target items-start justify-between gap-4 py-2">
      <div className="flex min-w-0 flex-col">
        <label htmlFor={id} className="text-body font-medium text-text">
          {label}
        </label>
        {description && (
          <p id={`${id}-d`} className="text-data text-text-muted">
            {description}
          </p>
        )}
      </div>
      <span className="relative mt-1 inline-flex h-6 w-12 shrink-0 items-center">
        <input
          id={id}
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          aria-describedby={description ? `${id}-d` : undefined}
          onChange={(e) => onChange(e.target.checked)}
          className="peer absolute -inset-3 z-10 m-0 cursor-pointer opacity-0 disabled:cursor-not-allowed"
        />
        <span
          aria-hidden
          className="absolute inset-0 rounded-pill border border-border bg-surface-raised transition-colors duration-(--dur-fast) peer-checked:border-voice-assistant peer-checked:bg-voice-assistant peer-disabled:opacity-50 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus"
        />
        <span
          aria-hidden
          className="absolute left-1 size-4 rounded-pill bg-text-muted transition-transform duration-(--dur-fast) peer-checked:translate-x-6 peer-checked:bg-on-accent motion-reduce:transition-none"
        />
      </span>
    </div>
  )
}
