import { AnimatePresence, motion } from 'motion/react'
import { useId, useState } from 'react'
import type { ToolCall } from '../state/types'
import { enter, exit } from '../styles/motion'
import { api } from '../api/client'
import { TOOL_LABEL } from './panels/toolLabels'
import { Icon, type IconName } from './Icon'

const RUNNING_COPY: Record<ToolCall['name'], string> = {
  web_search: 'Searching the web…',
  weather: 'Checking the weather…',
  memory_read: 'Checking memory…',
  memory_write: 'Saving to memory…',
  memory_delete: 'Deleting a memory…',
  memory_suggest: 'Suggesting a memory…',
  task_list: 'Checking your tasks…',
  task_add: 'Adding the task…',
  task_update: 'Updating the task…',
  task_delete: 'Deleting the task…',
  calendar_list: 'Checking your calendar…',
  calendar_add: 'Adding to your calendar…',
  calendar_update: 'Moving the calendar block…',
  calendar_delete: 'Removing the calendar block…',
  reminder_set: 'Setting the reminder…',
  reminder_update: 'Changing the reminder…',
  day_plan_propose: 'Planning your day…',
  day_plan_apply: 'Applying your plan…',
  skill_run: 'Running a skill…',
}

const FAILED_COPY: Record<ToolCall['name'], string> = {
  web_search: "Couldn't reach web search",
  weather: "Couldn't reach weather service",
  memory_read: "Couldn't read memory",
  memory_write: "Couldn't save to memory",
  memory_delete: "Couldn't delete the memory",
  memory_suggest: "Couldn't save the suggestion",
  task_list: "Couldn't read your tasks",
  task_add: "Couldn't add the task",
  task_update: "Couldn't update the task",
  task_delete: "Couldn't delete the task",
  calendar_list: "Couldn't read your calendar",
  calendar_add: "Couldn't add to your calendar",
  calendar_update: "Couldn't move the calendar block",
  calendar_delete: "Couldn't remove the calendar block",
  reminder_set: "Couldn't set the reminder",
  reminder_update: "Couldn't change the reminder",
  day_plan_propose: "Couldn't plan your day",
  day_plan_apply: "Couldn't apply the plan",
  skill_run: "Couldn't finish the skill",
}

const DONE_COPY: Record<Exclude<ToolCall['name'], 'web_search'>, string> = {
  weather: 'Weather from Open-Meteo',
  memory_read: 'Checked memory',
  memory_write: 'Saved to memory',
  memory_delete: 'Memory deleted',
  memory_suggest: 'Suggested a memory for your OK',
  task_list: 'Checked your tasks',
  task_add: 'Task added',
  task_update: 'Task updated',
  task_delete: 'Task deleted',
  calendar_list: 'Checked your calendar',
  calendar_add: 'Added to your calendar',
  calendar_update: 'Calendar block moved',
  calendar_delete: 'Calendar block removed',
  reminder_set: 'Reminder set',
  reminder_update: 'Reminder changed',
  day_plan_propose: 'Plan ready for your OK',
  day_plan_apply: 'Plan applied',
  skill_run: 'Skill finished',
}

/** The user said no, or the call stopped before it ran: nothing changed. */
const DECLINED_COPY: Partial<Record<ToolCall['name'], string>> = {
  memory_delete: 'Cancelled. Your memory was kept.',
  memory_write: 'Cancelled. Nothing was saved.',
}

function outcomeCopy(call: ToolCall) {
  if (call.status === 'cancelled') return 'Stopped before it ran. Nothing changed.'
  if (call.status === 'expired') return 'No answer in time. Nothing changed.'
  return DECLINED_COPY[call.name] ?? 'Cancelled. Nothing changed.'
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

/** A chip for a change that can be undone (plan P4): "Memory deleted · Undo". */
function UndoableChip({ call, label, icon }: { call: ToolCall; label: string; icon: IconName }) {
  const [state, setState] = useState<'idle' | 'undoing' | 'undone' | 'failed'>('idle')
  const undo = async () => {
    if (!call.actionId) return
    setState('undoing')
    try {
      await api.undoAction(call.actionId)
      setState('undone')
    } catch {
      setState('failed')
    }
  }
  if (state === 'undone') {
    return (
      <span className={`${staticChip} border-border text-text-muted`}>
        <Icon name="retry" className="size-4" />
        Undone
      </span>
    )
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className={`${staticChip} border-border text-text-muted`}>
        <Icon name={icon} className="size-4 text-voice-assistant" />
        {label}
      </span>
      <button
        type="button"
        onClick={() => void undo()}
        disabled={state === 'undoing'}
        className={`${buttonChip} cursor-pointer border-border text-text transition-colors duration-(--dur-fast) hover:border-text-subtle disabled:opacity-60`}
      >
        {state === 'failed' ? "Couldn't undo. Try again" : 'Undo'}
      </button>
    </span>
  )
}

export function ToolChip({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const toolIcon = TOOL_LABEL[call.name].icon

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

  if (call.status === 'declined' || call.status === 'cancelled' || call.status === 'expired') {
    return (
      <span className={`${staticChip} border-border text-text-muted`}>
        <Icon name="close" className="size-4" />
        {outcomeCopy(call)}
      </span>
    )
  }

  const sources = call.sources ?? []
  if (call.status === 'done' && call.undoable && call.actionId) {
    return <UndoableChip call={call} label={doneCopy(call)} icon={toolIcon} />
  }
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
