import { useId } from 'react'

interface ChoiceRowProps<T extends string> {
  label: string
  description?: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}

/** A segmented choice: real radio buttons, so arrow keys and screen readers work. */
export function ChoiceRow<T extends string>({ label, description, value, options, onChange }: ChoiceRowProps<T>) {
  const id = useId()
  return (
    <fieldset className="flex flex-col gap-2 py-2" aria-describedby={description ? `${id}-d` : undefined}>
      <legend className="text-body font-medium text-text">{label}</legend>
      {description && (
        <p id={`${id}-d`} className="text-data text-text-muted">
          {description}
        </p>
      )}
      <div className="grid grid-cols-3 gap-1 rounded-pill border border-border bg-bg p-1">
        {options.map((option) => (
          <label
            key={option.value}
            className="relative flex min-h-target cursor-pointer items-center justify-center rounded-pill px-3 text-body text-text-muted transition-colors duration-(--dur-fast) has-[:checked]:bg-field-line has-[:checked]:text-field-glow has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus hover:text-text"
          >
            <input
              type="radio"
              name={id}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
