import type { ReactNode } from 'react'
import type { Resource } from '../../api/useResource'

/** Loading, error and ready states shared by the three panels. */
export function ResourceView<T>({
  state,
  onRetry,
  children,
}: {
  state: Resource<T>
  onRetry: () => void
  children: (data: T) => ReactNode
}) {
  if (state.status === 'loading') {
    return (
      <p role="status" className="font-mono text-label uppercase text-text-muted">
        Loading…
      </p>
    )
  }
  if (state.status === 'error') {
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <p className="text-body text-text">{state.message}</p>
        <button
          type="button"
          onClick={onRetry}
          className="min-h-target rounded-pill border border-border px-4 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle"
        >
          Try again
        </button>
      </div>
    )
  }
  return <>{children(state.data)}</>
}

export const iconButton =
  'grid size-12 place-items-center rounded-card text-text-muted transition-colors duration-(--dur-fast) hover:bg-surface-raised hover:text-text'

export const secondaryButton =
  'inline-flex min-h-target items-center justify-center gap-2 rounded-pill border border-border px-4 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:border-border'

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="mb-3 font-mono text-label font-medium uppercase text-text-muted">{children}</h3>
}
