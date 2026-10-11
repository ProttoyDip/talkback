import { useEffect, useRef, useState } from 'react'
import { sendSignInLink, signInAsGuest } from '../api/auth'
import { AccessCodeError, requestSession, saveAccessCode, savedAccessCode } from '../api/session'
import { Icon } from '../components/Icon'
import { secondaryButton } from '../components/panels/shared'
import { REPLAY_HREF } from './AccessGate'

const primary =
  'min-h-target self-start rounded-pill bg-voice-assistant px-8 font-medium text-on-accent transition-transform duration-(--dur-instant) active:scale-[0.97] disabled:opacity-60'
const field = 'min-h-target rounded-input border border-border bg-surface px-3 text-body text-text'

type Status = 'idle' | 'sending' | 'sent' | 'joining' | 'send-failed' | 'wrong-code' | 'offline'

/**
 * Accounts are on (plan P2): sign in with an email link, or continue as a
 * guest. Each person's memories and settings are their own. When the server
 * has an access code, everyone types it first (SECURITY.md T8).
 */
export function SignIn({ needsCode, onPass }: { needsCode: boolean; onPass: () => void }) {
  const [code, setCode] = useState(savedAccessCode)
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const first = useRef<HTMLInputElement>(null)

  useEffect(() => first.current?.focus(), [])

  const keepCode = () => {
    if (needsCode) saveAccessCode(code.trim())
  }

  const sendLink = async () => {
    if (!email.trim()) return
    keepCode()
    setStatus('sending')
    try {
      await sendSignInLink(email.trim())
      setStatus('sent')
    } catch {
      setStatus('send-failed')
    }
  }

  const joinAsGuest = async () => {
    keepCode()
    setStatus('joining')
    try {
      await signInAsGuest()
      await requestSession()
      onPass()
    } catch (error) {
      setStatus(error instanceof AccessCodeError ? 'wrong-code' : 'offline')
    }
  }

  const message: Partial<Record<Status, string>> = {
    'send-failed': "We couldn't send the link. Check the address, or try again in a minute.",
    'wrong-code': "That code didn't work. Check it and try again.",
    offline: 'The server is not reachable. Try again.',
  }
  const busy = status === 'sending' || status === 'joining'
  const codeMissing = needsCode && !code.trim()

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-12 sm:px-8">
      <div className="flex w-full max-w-stage flex-col gap-6 sm:max-w-[calc(var(--stage-max-width)/2)]">
        <p className="text-transcript text-text">
          TalkBack is a voice assistant you can interrupt. Talk naturally, cut in any time, and it remembers what you
          ask it to.
        </p>
        <h1 className="font-display text-h1 font-extrabold">Sign in to talk.</h1>
        <p className="text-body text-text-muted">Your memories and settings are yours alone.</p>

        {needsCode && (
          <div className="flex flex-col gap-2">
            <label htmlFor="signin-code" className="text-body font-medium text-text">
              Access code
            </label>
            <input
              ref={first}
              id="signin-code"
              type="password"
              autoComplete="off"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className={field}
            />
            <p className="text-data text-text-muted">The demo is shared with a code. Ask whoever sent you the link.</p>
          </div>
        )}

        {status === 'sent' ? (
          <p role="status" className="rounded-card border border-border bg-surface p-4 text-body text-text">
            Check your email. The link signs you in on this device.
          </p>
        ) : (
          <form
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              void sendLink()
            }}
          >
            <label htmlFor="signin-email" className="text-body font-medium text-text">
              Email
            </label>
            <input
              ref={needsCode ? undefined : first}
              id="signin-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={field}
            />
            <button type="submit" disabled={busy || codeMissing || !email.trim()} className={`${primary} mt-2`}>
              {status === 'sending' ? 'Sending…' : 'Send sign-in link'}
            </button>
          </form>
        )}

        {message[status] && (
          <p role="alert" className="text-data text-danger">
            {message[status]}
          </p>
        )}

        <div className="flex flex-col gap-3 border-t border-border pt-6">
          <button
            type="button"
            disabled={busy || codeMissing}
            onClick={() => void joinAsGuest()}
            className={`${secondaryButton} self-start`}
          >
            {status === 'joining' ? 'Joining…' : 'Continue as guest'}
          </button>
          <p className="text-data text-text-muted">
            No email needed. Your memories stay with this browser until you sign out.
          </p>
          <a href={REPLAY_HREF} className={`${secondaryButton} self-start`}>
            <Icon name="play" className="size-4" />
            Watch the recorded demo
          </a>
        </div>
      </div>
    </main>
  )
}
