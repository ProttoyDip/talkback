import { motion } from 'motion/react'
import { useEffect, useRef } from 'react'
import { enter, exit } from '../styles/motion'
import { Icon } from './Icon'
import type { Panel } from './Navigation'

const TITLES: Record<Panel, string> = { memory: 'Memory', skills: 'Skills' }

/*
 * Memory and Skills panels are later steps (design.md 5.3, 5.4). Until then
 * the drawer shows their empty states, which are real states of the product.
 */
function EmptyState({ panel }: { panel: Panel }) {
  if (panel === 'memory') {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-body text-text">Nothing remembered yet.</p>
        <p className="text-body text-text-muted">
          Try: <span className="text-voice-user">“Remember that I prefer Celsius.”</span>
        </p>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body text-text">No skills yet.</p>
      <p className="text-body text-text-muted">
        Skills like <span className="font-mono text-data text-text">morning brief</span> appear
        here once they are added.
      </p>
    </div>
  )
}

/**
 * Right drawer, 360 px on desktop; a full-height sheet below 1024 px
 * (design.md 4).
 */
export function Drawer({ panel, onClose }: { panel: Panel; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    closeRef.current?.focus()
  }, [panel])

  return (
    <motion.aside
      aria-label={TITLES[panel]}
      className="fixed inset-0 z-40 flex flex-col bg-surface lg:sticky lg:top-0 lg:z-auto lg:h-dvh lg:w-drawer lg:shrink-0 lg:border-l lg:border-border"
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0, transition: enter }}
      exit={{ opacity: 0, x: 24, transition: exit }}
    >
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <h2 className="font-display text-h2 font-bold">{TITLES[panel]}</h2>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label={`Close ${TITLES[panel]}`}
          className="grid size-12 place-items-center rounded-card text-text-muted transition-colors duration-(--dur-fast) hover:bg-surface-raised hover:text-text"
        >
          <Icon name="close" className="size-6" />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto p-6">
        <EmptyState panel={panel} />
      </div>
    </motion.aside>
  )
}
