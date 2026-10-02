import { motion } from 'motion/react'
import { useEffect, useRef } from 'react'
import { enter, exit } from '../styles/motion'
import { Icon } from './Icon'
import type { ConversationModel } from '../session/model'
import { MemoryPanel } from './panels/MemoryPanel'
import { SettingsPanel } from './panels/SettingsPanel'
import { SkillsPanel } from './panels/SkillsPanel'
import type { Panel } from './Navigation'

const TITLES: Record<Panel, string> = { memory: 'Memory', skills: 'Skills', settings: 'Settings' }

/**
 * Right drawer, 360 px on desktop; a full-height sheet below 1024 px
 * (design.md 4).
 */
export interface DrawerContext {
  /** Changes when TalkBack saves a memory, so the open list refreshes. */
  memoryVersion?: string
  sessionOpen: boolean
  onSkillRan: (name: string) => void
  activeModels: ConversationModel['models']
}

export function Drawer({ panel, onClose, context }: { panel: Panel; onClose: () => void; context: DrawerContext }) {
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
        {panel === 'memory' && <MemoryPanel refreshKey={context.memoryVersion} />}
        {panel === 'skills' && <SkillsPanel sessionOpen={context.sessionOpen} onRan={context.onSkillRan} />}
        {panel === 'settings' && <SettingsPanel active={context.activeModels} />}
      </div>
    </motion.aside>
  )
}
