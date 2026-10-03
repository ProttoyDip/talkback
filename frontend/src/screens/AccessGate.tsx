import { useEffect, useRef, useState } from 'react'
import { AccessCodeError, requestSession, saveAccessCode } from '../api/session'

/**
 * Public demo gate (SECURITY.md T8). Shown only when the server has an
 * access code set and this browser has not given the right one yet.
 */
export function AccessGate({ onPass }: { onPass: () => void }) {
  const [code, setCode] = useState('')
  const [status, setStatus] = useState<'idle' | 'checking' | 'wrong' | 'offline'>('idle')
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => input.current?.focus(), [])

  const submit = async () => {
    const value = code.trim()
    if (!value) return
    setStatus('checking')
    try {
      await requestSession(value)
      saveAccessCode(value)
      onPass()
    } catch (error) {
      setStatus(error instanceof AccessCodeError ? 'wrong' : 'offline')
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-12 sm:px-8">
      <form
        className="flex w-full max-w-stage flex-col gap-6 sm:max-w-[calc(var(--stage-max-width)/2)]"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <h1 className="font-display text-h1 font-extrabold">This demo needs an access code.</h1>
        <p className="text-body text-text-muted">
          It keeps the shared demo for the people it was sent to. Ask whoever shared the link.
        </p>
        <div className="flex flex-col gap-2">
          <label htmlFor="access-code" className="text-body font-medium text-text">
            Access code
          </label>
          <input
            ref={input}
            id="access-code"
            type="password"
            autoComplete="off"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            aria-describedby={status === 'wrong' || status === 'offline' ? 'access-error' : undefined}
            className="min-h-target rounded-input border border-border bg-surface px-3 text-body text-text"
          />
          {(status === 'wrong' || status === 'offline') && (
            <p id="access-error" role="alert" className="text-data text-danger">
              {status === 'wrong' ? "That code didn't work. Check it and try again." : 'The server is not reachable. Try again.'}
            </p>
          )}
        </div>
        <button
          type="submit"
          disabled={status === 'checking' || !code.trim()}
          className="min-h-target self-start rounded-pill bg-voice-assistant px-8 font-medium text-on-accent transition-transform duration-(--dur-instant) active:scale-[0.97] disabled:opacity-60"
        >
          {status === 'checking' ? 'Checking…' : 'Continue'}
        </button>
      </form>
    </main>
  )
}
