import { motion } from 'motion/react'
import type { ConfirmRequest } from '../state/types'
import { enter, exit } from '../styles/motion'
import { Icon } from './Icon'

interface ConfirmCardProps {
  request: ConfirmRequest
  onAnswer: (approved: boolean) => void
  className?: string
}

/**
 * Approval for a sensitive action (design.md 5.2, SECURITY.md T5).
 * Voice answers work too, so the copy says so.
 */
export function ConfirmCard({ request, onAnswer, className = '' }: ConfirmCardProps) {
  return (
    <motion.section
      role="alertdialog"
      aria-labelledby={`confirm-${request.callId}`}
      aria-live="assertive"
      className={`flex flex-col gap-4 rounded-card border border-warning bg-surface p-4 sm:p-6 ${className}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0, transition: enter }}
      exit={{ opacity: 0, y: 8, transition: exit }}
    >
      <div className="flex items-start gap-3">
        <Icon name="alert" className="mt-1 size-4 shrink-0 text-warning" />
        <div className="flex flex-col gap-1">
          <p className="font-mono text-label font-medium uppercase text-warning">Needs your OK</p>
          <p id={`confirm-${request.callId}`} className="text-transcript text-text">
            {request.summary}
          </p>
          <p className="text-body text-text-muted">Say “yes” or “no”, or choose below.</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-3 sm:pl-8">
        <button
          type="button"
          onClick={() => onAnswer(true)}
          className="min-h-target rounded-pill bg-warning px-6 font-medium text-bg transition-transform duration-(--dur-instant) active:scale-[0.97]"
        >
          Yes, do it
        </button>
        <button
          type="button"
          onClick={() => onAnswer(false)}
          className="min-h-target rounded-pill border border-border px-6 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle"
        >
          No
        </button>
      </div>
    </motion.section>
  )
}
