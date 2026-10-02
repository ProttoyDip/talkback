import { AnimatePresence, motion } from 'motion/react'
import { useId, useState } from 'react'
import type { ToolCall } from '../state/types'
import { enter, exit } from '../styles/motion'
import { Icon } from './Icon'

const RUNNING_COPY: Record<ToolCall['name'], string> = {
  web_search: 'Searching the web…',
  weather: 'Checking the weather…',
  memory_read: 'Checking memory…',
  memory_write: 'Saving to memory…',
  memory_delete: 'Deleting a memory…',
  skill_run: 'Running a skill…',
}

const FAILED_COPY: Record<ToolCall['name'], string> = {
  web_search: "Couldn't reach web search",
  weather: "Couldn't reach weather service",
  memory_read: "Couldn't read memory",
  memory_write: "Couldn't save to memory",
  memory_delete: "Couldn't delete the memory",
  skill_run: "Couldn't finish the skill",
}

const DONE_COPY: Record<Exclude<ToolCall['name'], 'web_search'>, string> = {
  weather: 'Weather from Open-Meteo',
  memory_read: 'Checked memory',
  memory_write: 'Saved to memory',
  memory_delete: 'Memory deleted',
  skill_run: 'Skill finished',
}

function doneCopy(call: ToolCall) {
  if (call.name !== 'web_search') return DONE_COPY[call.name]
  const n = call.sources?.length ?? 0
  return n === 1 ? '1 source' : `${n} sources`
}

const chip = 'inline-flex items-center gap-2 rounded-input border px-3 font-mono text-data'
// Static chips are labels, not controls, so they stay compact. The sources
// toggle looks the same but its hit area extends to 48 px (design.md 7).
const staticChip = `${chip} h-8`
const buttonChip = `${chip} relative h-8 after:absolute after:inset-x-0 after:-inset-y-2`

export function ToolChip({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const toolIcon = call.name === 'weather' ? 'weather' : call.name === 'web_search' ? 'globe' : call.name === 'skill_run' ? 'skills' : 'memory'

  if (call.status === 'running') {
    return (
      <span className={`${staticChip} border-border text-text-muted`}>
        <span
          aria-hidden
          className="size-3 rounded-pill border-2 border-border border-t-voice-assistant motion-safe:animate-spin"
        />
        {RUNNING_COPY[call.name]}
      </span>
    )
  }

  if (call.status === 'failed') {
    return (
      <span className={`${staticChip} border-danger text-danger`}>
        <Icon name="alert" className="size-4" />
        {FAILED_COPY[call.name]}
      </span>
    )
  }

  const sources = call.sources ?? []
  if (sources.length === 0) {
    return (
      <span className={`${staticChip} border-border text-text-muted`}>
        <Icon name={toolIcon} className="size-4 text-voice-assistant" />
        {doneCopy(call)}
      </span>
    )
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
        className={`${buttonChip} cursor-pointer border-border text-text-muted transition-colors duration-(--dur-fast) hover:border-text-subtle hover:text-text`}
      >
        <Icon name={toolIcon} className="size-4 text-voice-assistant" />
        {doneCopy(call)}
        <Icon
          name="chevron"
          className={`size-4 transition-transform duration-(--dur-fast) ease-enter ${open ? 'rotate-180' : ''}`}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.ol
            id={listId}
            className="flex flex-col gap-1"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4, transition: exit }}
            transition={enter}
          >
            {sources.map((s, i) => (
              <li key={s.url}>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="group inline-flex min-h-target items-center gap-3 rounded-input px-2 text-body text-text-muted hover:text-text"
                >
                  <span className="tabular font-mono text-label text-text-subtle">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="underline decoration-border underline-offset-4 group-hover:decoration-text-muted">
                    {s.title}
                  </span>
                  <Icon name="external" className="size-4 shrink-0" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              </li>
            ))}
          </motion.ol>
        )}
      </AnimatePresence>
    </div>
  )
}
