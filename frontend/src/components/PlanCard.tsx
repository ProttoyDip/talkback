import { motion } from 'motion/react'
import { useState } from 'react'
import { api } from '../api/client'
import type { DayPlan } from '../session/model'
import { enter, exit } from '../styles/motion'
import { Icon } from './Icon'

/** The wall-clock time in the plan's own time zone (the server's local time), not the browser's. */
const time = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }).format(
    new Date(`${iso.slice(0, 16)}Z`),
  )

const OUTCOME: Partial<Record<DayPlan['status'], string>> = {
  rejected: 'Not now. Your calendar is unchanged.',
  superseded: 'Replaced by a newer plan.',
  expired: 'This plan expired. Ask again for a fresh one.',
}

/**
 * "Prepare my day" (plan P6): the proposed blocks with their reasons. The
 * user picks which to add; nothing changes until they do. Adding is one
 * action, so Undo removes the whole plan.
 */
export function PlanCard({ plan, className = '' }: { plan: DayPlan; className?: string }) {
  const [chosen, setChosen] = useState<number[]>(() => plan.items.map((i) => i.index))
  const [local, setLocal] = useState<{ status: DayPlan['status']; applied?: number[]; actionId?: string }>()
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string>()
  const [undone, setUndone] = useState(false)
  const status = local?.status ?? plan.status
  const applied = local?.applied ?? plan.applied ?? []
  const actionId = local?.actionId ?? plan.actionId

  const accept = async () => {
    setBusy(true)
    setProblem(undefined)
    try {
      const result = await api.applyPlan(plan.id, chosen)
      setLocal({ status: result.status, applied: result.applied, actionId: result.action_id ?? undefined })
    } catch {
      setProblem('That did not work. The plan may have expired; ask again for a fresh one.')
    }
    setBusy(false)
  }

  const decline = async () => {
    try {
      await api.rejectPlan(plan.id)
      setLocal({ status: 'rejected' })
    } catch {
      setProblem('That plan was already answered. Check your calendar in the Plan panel.')
    }
  }

  const tick = (index: number, on: boolean) => {
    const next = on ? [...chosen, index] : chosen.filter((i) => i !== index)
    setChosen(next)
    // Saved, so a spoken "yes" applies just these.
    void api.choosePlanItems(plan.id, next).catch(() => {})
  }

  const undo = async () => {
    if (!actionId) return
    try {
      await api.undoAction(actionId)
      setUndone(true)
    } catch {
      setProblem("Couldn't undo: a block changed since. Remove it in the Plan panel.")
    }
  }

  const done = status === 'accepted' || status === 'partially_applied'
  return (
    <motion.section
      aria-labelledby={`plan-${plan.id}`}
      className={`flex flex-col gap-4 rounded-card border border-voice-assistant bg-surface p-4 sm:p-6 ${className}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0, transition: enter }}
      exit={{ opacity: 0, y: 8, transition: exit }}
    >
      <div className="flex items-start gap-3">
        <Icon name="calendar" className="mt-1 size-4 shrink-0 text-voice-assistant" />
        <div className="flex flex-col gap-1">
          <p className="font-mono text-label font-medium uppercase text-voice-assistant">Your day</p>
          <h3 id={`plan-${plan.id}`} className="text-transcript text-text">
            {plan.items.length === 1 ? 'One block for your most urgent task' : `${plan.items.length} blocks for your most urgent tasks`}
          </h3>
        </div>
      </div>

      <fieldset className="flex flex-col gap-2 sm:pl-8" disabled={status !== 'proposed' || busy}>
        <legend className="sr-only">Blocks to add</legend>
        {plan.items.map((item) => (
          <label key={item.index} className="flex min-h-target items-start gap-3 text-body text-text">
            <input
              type="checkbox"
              className="mt-1 size-4 accent-(--voice-assistant)"
              checked={status === 'proposed' ? chosen.includes(item.index) : applied.includes(item.index)}
              onChange={(e) => tick(item.index, e.target.checked)}
            />
            <span>
              <span className="font-mono text-data text-text-muted">
                {time(item.starts_at)}–{time(item.ends_at)}
              </span>{' '}
              {item.title}
              <span className="block text-data text-text-muted">{item.reason}</span>
            </span>
          </label>
        ))}
      </fieldset>

      {problem && (
        <p role="alert" className="text-data text-danger sm:pl-8">
          {problem}
        </p>
      )}

      {status === 'proposed' && (
        <div className="flex flex-wrap gap-3 sm:pl-8">
          <button
            type="button"
            onClick={() => void accept()}
            disabled={busy || chosen.length === 0}
            className="min-h-target rounded-pill bg-voice-assistant px-6 font-medium text-on-accent transition-transform duration-(--dur-instant) active:scale-[0.97] disabled:opacity-60"
          >
            {busy ? 'Adding…' : `Add ${chosen.length} ${chosen.length === 1 ? 'block' : 'blocks'}`}
          </button>
          <button
            type="button"
            onClick={() => void decline()}
            className="min-h-target rounded-pill border border-border px-6 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle"
          >
            Not now
          </button>
        </div>
      )}

      {done && (
        <p role="status" className="flex flex-wrap items-center gap-3 text-body text-text sm:pl-8">
          {undone
            ? 'Undone. Your calendar is back as it was.'
            : status === 'partially_applied'
              ? `Added ${applied.length}. The others clashed with your calendar.`
              : 'Added to your calendar.'}
          {!undone && actionId && (
            <button
              type="button"
              onClick={() => void undo()}
              className="min-h-target rounded-pill border border-border px-4 font-medium text-text hover:border-text-subtle"
            >
              Undo
            </button>
          )}
        </p>
      )}
      {OUTCOME[status] && (
        <p role="status" className="text-body text-text-muted sm:pl-8">
          {OUTCOME[status]}
        </p>
      )}
    </motion.section>
  )
}
