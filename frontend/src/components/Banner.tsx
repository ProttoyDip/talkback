import { Icon, type IconName } from './Icon'

export interface BannerProps {
  message: string
  /** danger: something is broken; neutral: information (session ended). */
  tone: 'danger' | 'neutral'
  action?: { label: string; icon?: IconName; onClick: () => void }
}

/** Error and offline states (design.md 5.6): plain message plus a next step. */
export function Banner({ message, tone, action }: BannerProps) {
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={`flex flex-wrap items-center justify-between gap-3 rounded-card border bg-surface px-4 py-3 ${
        tone === 'danger' ? 'border-danger' : 'border-border'
      }`}
    >
      <p className="flex items-center gap-3 text-body text-text">
        <Icon
          name="alert"
          className={`size-4 shrink-0 ${tone === 'danger' ? 'text-danger' : 'text-text-muted'}`}
        />
        {message}
      </p>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="inline-flex min-h-target items-center gap-2 rounded-pill border border-border px-4 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle"
        >
          <Icon name={action.icon ?? 'retry'} className="size-4" />
          {action.label}
        </button>
      )}
    </div>
  )
}
