import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

export type Panel = 'memory' | 'skills' | 'settings'

interface NavProps {
  openPanel: Panel | null
  onTogglePanel: (panel: Panel) => void
}

interface Item {
  id: 'conversation' | Panel
  label: string
  icon: IconName
  shortcut?: string
}

const ITEMS: Item[] = [
  { id: 'conversation', label: 'Conversation', icon: 'conversation' },
  { id: 'memory', label: 'Memory', icon: 'memory', shortcut: 'M' },
  { id: 'skills', label: 'Skills', icon: 'skills', shortcut: 'K' },
  { id: 'settings', label: 'Settings', icon: 'settings' },
]

function NavButton({
  item,
  openPanel,
  onTogglePanel,
  compact,
}: NavProps & { item: Item; compact: boolean }) {
  const isPanel = item.id !== 'conversation'
  const active = isPanel ? openPanel === item.id : item.id === 'conversation' && openPanel === null
  const base =
    'group relative flex items-center justify-center rounded-card transition-colors duration-(--dur-fast)'
  const size = compact ? 'min-h-target min-w-target flex-col gap-1 px-2' : 'size-12'
  const tone = active ? 'bg-surface-raised text-text' : 'text-text-muted hover:bg-surface hover:text-text'

  return (
    <button
      type="button"
      aria-label={item.label}
      aria-current={active && !isPanel ? 'page' : undefined}
      aria-expanded={isPanel ? openPanel === item.id : undefined}
      aria-keyshortcuts={item.shortcut}
      onClick={() => {
        if (isPanel) onTogglePanel(item.id as Panel)
        else if (openPanel) onTogglePanel(openPanel)
      }}
      className={`${base} ${size} ${tone}`}
    >
      {active && !compact && (
        <span aria-hidden className="absolute inset-y-3 -left-2 w-px bg-voice-assistant" />
      )}
      <Icon name={item.icon} className="size-6" />
      {compact ? (
        <span className="hidden font-mono text-label uppercase sm:block">{item.label}</span>
      ) : (
        <span
          role="tooltip"
          className="pointer-events-none invisible absolute left-[calc(100%+var(--space-3))] z-20 whitespace-nowrap rounded-input border border-border bg-surface-raised px-3 py-1 font-mono text-label uppercase text-text opacity-0 shadow-popover transition-opacity duration-(--dur-fast) group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100"
        >
          {item.label}
          {item.shortcut && <span className="text-text-muted"> · {item.shortcut}</span>}
        </span>
      )}
    </button>
  )
}

/** Desktop left rail, 64 px (design.md 4). */
export function NavRail(props: NavProps) {
  return (
    <nav
      aria-label="Main"
      className="sticky top-0 hidden h-dvh w-rail shrink-0 flex-col items-center gap-2 border-r border-border py-4 lg:flex"
    >
      <span aria-hidden className="mb-4 flex h-8 items-center gap-1">
        <span className="h-4 w-1 rounded-pill bg-voice-user" />
        <span className="h-6 w-1 rounded-pill bg-voice-assistant" />
        <span className="h-3 w-1 rounded-pill bg-voice-assistant" />
      </span>
      {ITEMS.map((item) => (
        <NavButton key={item.id} item={item} compact={false} {...props} />
      ))}
    </nav>
  )
}

/**
 * Tablet and mobile bottom bar (design.md 4). The mic sits in the centre,
 * fixed at the bottom with its 72 px target.
 */
export function TabBar({ mic, ...props }: NavProps & { mic: ReactNode }) {
  const [left, right] = [ITEMS.slice(0, 2), ITEMS.slice(2)]
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-bg px-2 pb-[max(var(--space-2),env(safe-area-inset-bottom))] pt-2 lg:hidden"
    >
      <div className="mx-auto grid max-w-stage grid-cols-[1fr_auto_1fr] items-end gap-2">
        <div className="flex justify-around">
          {left.map((item) => (
            <NavButton key={item.id} item={item} compact {...props} />
          ))}
        </div>
        <div className="-mt-8">{mic}</div>
        <div className="flex justify-around">
          {right.map((item) => (
            <NavButton key={item.id} item={item} compact {...props} />
          ))}
        </div>
      </div>
    </nav>
  )
}
