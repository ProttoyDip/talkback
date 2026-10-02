import { useCallback, useEffect, useEffectEvent, useState } from 'react'
import { ApiError } from './client'

export type Resource<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: T }

/** Loads on mount and whenever `key` changes; `reload` retries. */
export function useResource<T>(load: () => Promise<T>, key: string) {
  const [state, setState] = useState<Resource<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const run = useEffectEvent(load)

  useEffect(() => {
    let cancelled = false
    run().then(
      (data) => {
        if (!cancelled) setState({ status: 'ready', data })
      },
      (error: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', message: error instanceof ApiError ? error.message : 'Something went wrong.' })
        }
      },
    )
    return () => {
      cancelled = true
    }
  }, [key, attempt])

  const reload = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((n) => n + 1)
  }, [])
  /** Replace the data without a round trip (after a successful edit). */
  const set = useCallback((data: T) => setState({ status: 'ready', data }), [])
  return { state, reload, set }
}
