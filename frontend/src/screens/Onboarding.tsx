import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import { markOnboarded } from './onboarded'
import { enter, exit } from '../styles/motion'

/** design.md 5.6: name the browser so the steps match what the user sees. */
function browserName(): string {
  const ua = navigator.userAgent
  if (/Edg\//.test(ua)) return 'Edge'
  if (/Firefox\//.test(ua)) return 'Firefox'
  if (/Chrome\//.test(ua)) return 'Chrome'
  if (/Safari\//.test(ua)) return 'Safari'
  return 'your browser'
}

function blockedHelp(): string {
  const browser = browserName()
  if (browser === 'Firefox') {
    return 'Microphone is blocked. Click the permissions icon in the address bar, remove the block for the microphone, then try again.'
  }
  if (browser === 'Safari') {
    return 'Microphone is blocked. Open Safari settings, choose Websites, then Microphone, and allow this site. Then try again.'
  }
  return `Microphone is blocked. Click the icon at the left of the ${browser} address bar and allow the microphone. Then try again.`
}

type MicResult = 'idle' | 'asking' | 'blocked' | 'missing'

const primary =
  'min-h-target self-start rounded-pill bg-voice-assistant px-8 font-medium text-on-accent transition-transform duration-(--dur-instant) active:scale-[0.97] disabled:opacity-60'

/**
 * First run (design.md 5.1): welcome, microphone permission, privacy promise.
 * `onStart` runs on the last click, which is also the user gesture browsers
 * need before audio can start. The headphones tip (step 4) shows afterwards,
 * on the conversation screen.
 */
export function Onboarding({ onStart }: { onStart: () => void }) {
  const [step, setStep] = useState(0)
  const [mic, setMic] = useState<MicResult>('idle')
  const headingRef = useRef<HTMLHeadingElement>(null)

  // Move focus to the new step's heading so screen readers announce it.
  useEffect(() => {
    headingRef.current?.focus()
  }, [step])

  const askMic = async () => {
    setMic('asking')
    try {
      // Only to trigger the browser's prompt. The real capture starts later.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((track) => track.stop())
      setMic('idle')
      setStep(2)
    } catch (error) {
      const name = error instanceof DOMException ? error.name : ''
      setMic(name === 'NotFoundError' ? 'missing' : 'blocked')
    }
  }

  const finish = () => {
    markOnboarded()
    onStart()
  }

  const dots = (
    <ol aria-label={`Step ${step + 1} of 3`} className="flex gap-2">
      {[0, 1, 2].map((i) => (
        <li key={i} aria-hidden className={`h-1 w-8 rounded-pill ${i <= step ? 'bg-voice-assistant' : 'bg-border'}`} />
      ))}
    </ol>
  )

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-12 sm:px-8">
      <div className="flex w-full max-w-stage flex-col gap-8">
        <span aria-hidden className="flex h-8 items-center gap-1">
          <span className="h-4 w-1 rounded-pill bg-voice-user" />
          <span className="h-6 w-1 rounded-pill bg-voice-assistant" />
          <span className="h-3 w-1 rounded-pill bg-voice-assistant" />
        </span>

        <AnimatePresence mode="wait">
          <motion.section
            key={step}
            className="flex flex-col gap-6"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0, transition: enter }}
            exit={{ opacity: 0, transition: exit }}
          >
            {step === 0 && (
              <>
                <h1 ref={headingRef} tabIndex={-1} className="font-display text-h1 font-extrabold outline-none sm:text-display">
                  Talk to me like a person.
                </h1>
                <p className="text-transcript text-text-muted">Interrupt me any time. I'll keep up.</p>
                <button type="button" className={primary} onClick={() => setStep(1)}>
                  Allow microphone
                </button>
              </>
            )}

            {step === 1 && (
              <>
                <h1 ref={headingRef} tabIndex={-1} className="font-display text-h1 font-extrabold outline-none">
                  I need your microphone.
                </h1>
                <p className="text-transcript text-text-muted">
                  TalkBack listens while it talks, so you can cut in. Your browser will ask for permission next.
                </p>
                {(mic === 'blocked' || mic === 'missing') && (
                  <p role="alert" className="flex items-start gap-3 rounded-card border border-danger bg-surface p-4 text-body text-text">
                    <Icon name="alert" className="mt-1 size-4 shrink-0 text-danger" />
                    {mic === 'blocked' ? blockedHelp() : 'No microphone was found. Plug one in, then try again.'}
                  </p>
                )}
                <button type="button" className={primary} disabled={mic === 'asking'} onClick={() => void askMic()}>
                  {mic === 'blocked' || mic === 'missing' ? 'Try again' : mic === 'asking' ? 'Waiting for your browser…' : 'Continue'}
                </button>
              </>
            )}

            {step === 2 && (
              <>
                <h1 ref={headingRef} tabIndex={-1} className="font-display text-h1 font-extrabold outline-none">
                  Your words stay yours.
                </h1>
                <ul className="flex flex-col gap-3 text-transcript text-text">
                  <li>Memories are kept in your private database.</li>
                  <li>No recordings are kept.</li>
                  <li>You can delete everything, any time.</li>
                </ul>
                <button type="button" className={primary} onClick={finish}>
                  Start talking
                </button>
              </>
            )}
          </motion.section>
        </AnimatePresence>

        {dots}
      </div>
    </main>
  )
}
