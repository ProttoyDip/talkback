import { useState } from 'react'
import type { ConversationModel } from '../session/model'
import { Icon } from './Icon'

type Resumable = NonNullable<ConversationModel['resumable']>

const button =
  'min-h-target rounded-pill border border-border px-4 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle'

/**
 * "Continue where you left off?" (plan P7): the earlier goal, what was done,
 * and what was still open. Open items are asked again, never run on their own.
 */
export function ResumeBanner({ state, onAnswer }: { state: Resumable; onAnswer: (accept: boolean) => void }) {
  const [answered, setAnswered] = useState<boolean | null>(null)
  if (answered !== null) {
    return answered ? (
      <p role="status" className="text-data text-text-muted">
        Continuing. TalkBack will check anything still open with you first.
      </p>
    ) : null
  }
  const answer = (accept: boolean) => {
    setAnswered(accept)
    onAnswer(accept)
  }
  return (
    <section aria-labelledby={`resume-${state.id}`} className="flex flex-col gap-3 rounded-card border border-border bg-surface px-4 py-3">
      <p id={`resume-${state.id}`} className="flex items-start gap-3 text-body text-text">
        <Icon name="retry" className="mt-1 size-4 shrink-0 text-voice-assistant" />
        <span>
          <span className="font-mono text-label uppercase text-text-muted">Continue where you left off?</span>
          <br />“{state.goal}”
        </span>
      </p>
      {state.decisions.length > 0 && (
        <div className="pl-7 text-data text-text-muted">
          Done then:
          <ul className="list-inside list-disc">
            {state.decisions.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {state.pending.length > 0 && (
        <div className="pl-7 text-data text-text-muted">
          Still open (TalkBack will ask again):
          <ul className="list-inside list-disc">
            {state.pending.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-2 pl-7">
        <button type="button" className={button} onClick={() => answer(true)}>
          Continue
        </button>
        <button type="button" className={button} onClick={() => answer(false)}>
          Start fresh
        </button>
      </div>
    </section>
  )
}
