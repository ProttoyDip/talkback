import { motion } from 'motion/react'
import { useEffect } from 'react'
import { enter, exit } from '../styles/motion'

export interface ToastData {
  id: string
  message: string
  action?: { label: string; onClick: () => void }
}

/** Shows for 4 s (design.md 11). Hovering or focusing pauses nothing: it is short and has no required action. */
const VISIBLE_MS = 4000

export function Toast({ toast, onDismiss }: { toast: ToastData; onDismiss: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, VISIBLE_MS)
    return () => clearTimeout(timer)
  }, [toast.id, onDismiss])

  return (
    <motion.div
      role="status"
      className="fixed inset-x-4 bottom-[calc(var(--mic-size)+var(--space-16))] z-50 mx-auto flex max-w-[calc(var(--stage-max-width)/2)] items-center justify-between gap-4 rounded-card border border-border bg-surface-raised px-4 py-2 shadow-popover lg:bottom-8"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0, transition: enter }}
      exit={{ opacity: 0, y: 8, transition: exit }}
    >
      <p className="min-w-0 truncate text-body text-text">{toast.message}</p>
      {toast.action && (
        <button
          type="button"
          onClick={() => {
            toast.action?.onClick()
            onDismiss()
          }}
          className="min-h-target shrink-0 rounded-input px-2 font-mono text-label font-medium uppercase text-voice-assistant hover:text-text"
        >
          {toast.action.label}
        </button>
      )}
    </motion.div>
  )
}
