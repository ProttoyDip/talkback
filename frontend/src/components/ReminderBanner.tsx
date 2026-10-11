import { api } from '../api/client'
import type { ReminderItem } from '../api/types'
import type { DueReminder } from '../session/useReminders'
import { askForNotifications } from '../session/useReminders'
import { when } from '../state/when'
import { Icon } from './Icon'

const button =
  'min-h-target rounded-pill border border-border px-4 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle'

/** Due (or missed) reminders, until the user answers each one (plan P5). */
export function ReminderBanner({ due, onDismiss }: { due: DueReminder[]; onDismiss: (reminder: ReminderItem) => void }) {
  if (due.length === 0) return null
  return (
    <ul aria-label="Reminders" className="flex flex-col gap-2">
      {due.map(({ reminder, missed }) => (
        <li
          key={reminder.id}
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-warning bg-surface px-4 py-3"
        >
          <p className="flex min-w-0 items-start gap-3 text-body text-text">
            <Icon name="bell" className="mt-1 size-4 shrink-0 text-warning" />
            <span>
              <span className="font-mono text-label uppercase text-warning">
                {missed ? `Missed while away · ${when(reminder.due_at)}` : 'Reminder'}
              </span>
              <br />
              {reminder.text}
            </span>
          </p>
          <span className="flex gap-2">
            <button
              type="button"
              className={button}
              onClick={() => {
                askForNotifications()
                void api.snoozeReminder(reminder.id, 10).catch(() => {})
                onDismiss(reminder)
              }}
            >
              Snooze 10 min
            </button>
            <button
              type="button"
              className={button}
              onClick={() => {
                askForNotifications()
                void api.reminderDone(reminder.id).catch(() => {})
                onDismiss(reminder)
              }}
            >
              Done
            </button>
          </span>
        </li>
      ))}
    </ul>
  )
}
