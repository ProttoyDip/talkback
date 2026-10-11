import { useId, useState } from 'react'
import { ApiError, api } from '../../api/client'
import type { EventItem, ReminderItem, TaskItem } from '../../api/types'
import { useResource } from '../../api/useResource'
import { Icon } from '../Icon'
import { dayInput, exact, localInput, when } from '../../state/when'
import { iconButton, ResourceView, secondaryButton } from './shared'

const field = 'min-h-target rounded-input border border-border bg-bg px-3 text-body text-text'
const card = 'flex flex-col gap-2 rounded-card border border-border bg-bg p-4'

function Problem({ message }: { message?: string }) {
  return message ? (
    <p role="alert" className="text-data text-danger">
      {message}
    </p>
  ) : null
}

function failure(error: unknown) {
  return error instanceof ApiError && error.status === 422
    ? 'Check the date and time and try again.'
    : 'That did not work. Try again.'
}

/** Tasks: today and later, a quick add, complete with one tap (each change is undoable in Activity). */
function Tasks({ refreshKey }: { refreshKey?: string }) {
  const { state, reload, set } = useResource(() => api.listTasks('open'), `tasks|${refreshKey ?? ''}`)
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')
  const [problem, setProblem] = useState<string>()
  const id = useId()

  const add = async (items: TaskItem[]) => {
    const value = title.trim()
    if (!value) return
    try {
      const task = await api.addTask({ title: value, due_at: due ? exact(due) : undefined })
      set([...items, task])
      setTitle('')
      setDue('')
      setProblem(undefined)
    } catch (error) {
      setProblem(failure(error))
    }
  }

  const complete = async (items: TaskItem[], task: TaskItem) => {
    try {
      await api.updateTask(task.id, { status: 'done' })
      set(items.filter((t) => t.id !== task.id))
    } catch (error) {
      setProblem(failure(error))
    }
  }

  const remove = async (items: TaskItem[], task: TaskItem) => {
    try {
      await api.deleteTask(task.id)
      set(items.filter((t) => t.id !== task.id))
    } catch (error) {
      setProblem(failure(error))
    }
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(items) => {
        const endOfToday = `${dayInput(new Date())}T23:59`
        const todayItems = items.filter((t) => t.due_at && localInput(new Date(t.due_at)) <= endOfToday)
        const later = items.filter((t) => t.due_at && localInput(new Date(t.due_at)) > endOfToday)
        const undated = items.filter((t) => !t.due_at)
        const group = (label: string, list: TaskItem[]) =>
          list.length > 0 && (
            <section aria-label={label} className="flex flex-col gap-2">
              <h3 className="font-mono text-label uppercase text-text-muted">{label}</h3>
              <ul className="flex flex-col gap-2">
                {list.map((task) => (
                  <li key={task.id} className={`${card} flex-row items-center`}>
                    <button
                      type="button"
                      className={iconButton}
                      aria-label={`Done: ${task.title}`}
                      onClick={() => void complete(items, task)}
                    >
                      <Icon name="task" className="size-6" />
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className="text-body text-text">
                        {task.title}
                        {task.priority === 'high' && (
                          <span className="ml-2 font-mono text-label uppercase text-warning">High</span>
                        )}
                      </p>
                      {task.due_at && <p className="text-data text-text-muted">{when(task.due_at)}</p>}
                    </div>
                    <button
                      type="button"
                      className={iconButton}
                      aria-label={`Delete task: ${task.title}`}
                      onClick={() => void remove(items, task)}
                    >
                      <Icon name="trash" className="size-6" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )
        return (
          <div className="flex flex-col gap-6">
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                void add(items)
              }}
            >
              <label htmlFor={`${id}-title`} className="text-body font-medium text-text">
                New task
              </label>
              <input id={`${id}-title`} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} className={field} />
              <label htmlFor={`${id}-due`} className="text-data text-text-muted">
                Due (optional)
              </label>
              <input
                id={`${id}-due`}
                type="datetime-local"
                value={due}
                onChange={(e) => setDue(e.target.value)}
                className={field}
              />
              <button type="submit" disabled={!title.trim()} className={`${secondaryButton} self-start`}>
                Add task
              </button>
              <Problem message={problem} />
            </form>
            {items.length === 0 ? (
              <p className="text-body text-text-muted">
                No open tasks. Try saying <span className="text-voice-user">“Add a task to call mom tomorrow.”</span>
              </p>
            ) : (
              <>
                {group('Today', todayItems)}
                {group('Later', later)}
                {group('No date', undated)}
              </>
            )}
          </div>
        )
      }}
    </ResourceView>
  )
}

/** Calendar: one day's blocks as a list, with a quick add. */
function Calendar({ refreshKey }: { refreshKey?: string }) {
  const [day, setDay] = useState(() => dayInput(new Date()))
  const next = new Date(`${day}T00:00`)
  next.setDate(next.getDate() + 1)
  const { state, reload, set } = useResource(
    () => api.listEvents(exact(`${day}T00:00`), exact(`${dayInput(next)}T00:00`)),
    `calendar|${day}|${refreshKey ?? ''}`,
  )
  const [title, setTitle] = useState('')
  const [start, setStart] = useState('09:00')
  const [end, setEnd] = useState('10:00')
  const [problem, setProblem] = useState<string>()
  const id = useId()

  const add = async (items: EventItem[]) => {
    if (!title.trim()) return
    try {
      const event = await api.addEvent({
        title: title.trim(),
        starts_at: exact(`${day}T${start}`),
        ends_at: exact(`${day}T${end}`),
      })
      set([...items, event].sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()))
      setTitle('')
      setProblem(undefined)
    } catch (error) {
      setProblem(failure(error))
    }
  }

  const remove = async (items: EventItem[], event: EventItem) => {
    try {
      await api.deleteEvent(event.id)
      set(items.filter((e) => e.id !== event.id))
    } catch (error) {
      setProblem(failure(error))
    }
  }

  const time = (iso: string) => new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(iso))

  return (
    <div className="flex flex-col gap-6">
      <label className="flex flex-col gap-1 text-body font-medium text-text">
        Day
        <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className={field} />
      </label>
      <ResourceView state={state} onRetry={reload}>
        {(items) => (
          <>
            {items.length === 0 ? (
              <p className="text-body text-text-muted">Nothing planned. Try saying “Block 2 to 4 for focus.”</p>
            ) : (
              <ol aria-label="Agenda" className="flex flex-col gap-2">
                {items.map((event) => (
                  <li key={event.id} className={`${card} flex-row items-center`}>
                    <div className="min-w-0 flex-1">
                    <p className="font-mono text-data text-text-muted">
                      {time(event.starts_at)}–{time(event.ends_at)}
                    </p>
                    <p className="text-body text-text">
                      {event.title}
                      {event.kind !== 'block' && (
                        <span className="ml-2 font-mono text-label uppercase text-text-muted">{event.kind}</span>
                      )}
                    </p>
                    </div>
                    <button
                      type="button"
                      className={iconButton}
                      aria-label={`Remove from calendar: ${event.title}`}
                      onClick={() => void remove(items, event)}
                    >
                      <Icon name="trash" className="size-6" />
                    </button>
                  </li>
                ))}
              </ol>
            )}
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                void add(items)
              }}
            >
              <label htmlFor={`${id}-title`} className="text-body font-medium text-text">
                New block
              </label>
              <input id={`${id}-title`} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} className={field} />
              <div className="flex gap-2">
                <label className="flex flex-1 flex-col gap-1 text-data text-text-muted">
                  From
                  <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={field} />
                </label>
                <label className="flex flex-1 flex-col gap-1 text-data text-text-muted">
                  To
                  <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={field} />
                </label>
              </div>
              <button type="submit" disabled={!title.trim()} className={`${secondaryButton} self-start`}>
                Add block
              </button>
              <Problem message={problem} />
            </form>
          </>
        )}
      </ResourceView>
    </div>
  )
}

/** Reminders waiting to go off, with a quick add. */
function Reminders({ refreshKey }: { refreshKey?: string }) {
  const { state, reload, set } = useResource(() => api.listReminders(), `reminders|${refreshKey ?? ''}`)
  const [text, setText] = useState('')
  const [due, setDue] = useState(() => {
    const soon = new Date(Date.now() + 60 * 60 * 1000)
    soon.setMinutes(0)
    return localInput(soon)
  })
  const [problem, setProblem] = useState<string>()
  const id = useId()

  const add = async (items: ReminderItem[]) => {
    if (!text.trim()) return
    try {
      const reminder = await api.setReminder({ text: text.trim(), due_at: exact(due) })
      set([...items, reminder].sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime()))
      setText('')
      setProblem(undefined)
    } catch (error) {
      setProblem(error instanceof ApiError && error.status === 422 ? 'Pick a time that has not passed.' : failure(error))
    }
  }

  const cancel = async (items: ReminderItem[], reminder: ReminderItem) => {
    try {
      await api.cancelReminder(reminder.id)
      set(items.filter((r) => r.id !== reminder.id))
    } catch (error) {
      setProblem(failure(error))
    }
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(items) => (
        <div className="flex flex-col gap-6">
          <form
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              void add(items)
            }}
          >
            <label htmlFor={`${id}-text`} className="text-body font-medium text-text">
              Remind me to
            </label>
            <input id={`${id}-text`} value={text} maxLength={300} onChange={(e) => setText(e.target.value)} className={field} />
            <label htmlFor={`${id}-due`} className="text-data text-text-muted">
              At
            </label>
            <input id={`${id}-due`} type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className={field} />
            <button type="submit" disabled={!text.trim()} className={`${secondaryButton} self-start`}>
              <Icon name="bell" className="size-4" />
              Set reminder
            </button>
            <Problem message={problem} />
            <p className="text-data text-text-muted">
              Reminders show here while TalkBack is open. If it is closed, they show as missed when you come back.
            </p>
          </form>
          {items.length === 0 ? (
            <p className="text-body text-text-muted">No reminders set.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {items.map((reminder) => (
                <li key={reminder.id} className={`${card} flex-row items-center`}>
                  <div className="min-w-0 flex-1">
                    <p className="text-body text-text">{reminder.text}</p>
                    <p className="text-data text-text-muted">{when(reminder.due_at)}</p>
                  </div>
                  <button
                    type="button"
                    className={iconButton}
                    aria-label={`Cancel reminder: ${reminder.text}`}
                    onClick={() => void cancel(items, reminder)}
                  >
                    <Icon name="close" className="size-6" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </ResourceView>
  )
}

const TABS = { tasks: 'Tasks', calendar: 'Calendar', reminders: 'Reminders' } as const

/** Plan P5: tasks, the day's calendar and reminders. Voice changes reload it (refreshKey). */
export function PlanPanel({ refreshKey }: { refreshKey?: string }) {
  const [tab, setTab] = useState<keyof typeof TABS>('tasks')
  const tabs = useId()
  return (
    <div className="flex min-h-full flex-col gap-4">
      <div role="tablist" aria-label="Plan" className="flex flex-wrap gap-2">
        {(Object.keys(TABS) as Array<keyof typeof TABS>).map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            id={`${tabs}-${name}`}
            aria-selected={tab === name}
            aria-controls={`${tabs}-panel`}
            onClick={() => setTab(name)}
            className={`min-h-target rounded-pill border px-4 font-medium transition-colors duration-(--dur-fast) ${
              tab === name ? 'border-voice-assistant text-text' : 'border-border text-text-muted hover:text-text'
            }`}
          >
            {TABS[name]}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${tabs}-panel`} aria-labelledby={`${tabs}-${tab}`}>
        {tab === 'tasks' && <Tasks refreshKey={refreshKey} />}
        {tab === 'calendar' && <Calendar refreshKey={refreshKey} />}
        {tab === 'reminders' && <Reminders refreshKey={refreshKey} />}
      </div>
    </div>
  )
}
