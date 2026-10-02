import { Icon } from './Icon'

/** Voice engine offline state (design.md 5.6). */
export function OfflineBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger bg-surface px-4 py-3"
    >
      <p className="flex items-center gap-3 text-body text-text">
        <Icon name="alert" className="size-4 shrink-0 text-danger" />
        The voice engine isn't reachable. Retrying in 5 seconds…
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex min-h-target items-center gap-2 rounded-pill border border-border px-4 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle"
      >
        <Icon name="retry" className="size-4" />
        Retry now
      </button>
    </div>
  )
}
