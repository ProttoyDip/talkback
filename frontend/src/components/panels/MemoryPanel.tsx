import { useEffect, useId, useState } from 'react'
import { ApiError, api } from '../../api/client'
import type { ActionItem, MemoryItem } from '../../api/types'
import { useResource } from '../../api/useResource'
import { Icon } from '../Icon'
import { SettingsToggleRow } from '../SettingsToggleRow'
import { iconButton, ResourceView, secondaryButton } from './shared'

/** Where a memory's words came from (SECURITY.md T3: shown so wrong ones are easy to spot). */
function SourceLine({ item }: { item: MemoryItem }) {
  if (item.source === 'assistant_suggestion') {
    return <p className="text-data text-text-muted">Suggested by TalkBack. Not used until you keep it.</p>
  }
  const verb = item.source === 'user_text' ? 'You typed' : item.source === 'user_edit' ? 'You edited' : 'You said'
  return item.utterance ? (
    <p className="text-data text-text-muted">
      {verb}: <span className="text-text">“{item.utterance}”</span>
    </p>
  ) : null
}

function savedAt(iso: string) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date)
}

function MemoryCard({
  item,
  onSaved,
  onDeleted,
}: {
  item: MemoryItem
  onSaved: (item: MemoryItem) => void
  onDeleted: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(item.text)
  const [failed, setFailed] = useState(false)

  const save = async () => {
    const text = draft.trim()
    if (!text || text === item.text) return setEditing(false)
    try {
      onSaved(await api.editMemory(item.id, { text }))
      setEditing(false)
      setFailed(false)
    } catch {
      setFailed(true)
    }
  }

  const decide = async (status: 'confirmed' | 'dismissed') => {
    try {
      const next = await api.editMemory(item.id, { status })
      if (status === 'dismissed') onDeleted(item.id)
      else onSaved(next)
    } catch {
      setFailed(true)
    }
  }

  const remove = async () => {
    try {
      await api.deleteMemory(item.id)
      onDeleted(item.id)
    } catch {
      setFailed(true)
    }
  }

  return (
    <li className="flex flex-col gap-2 rounded-card border border-border bg-bg p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-label font-medium uppercase text-voice-user">
          {item.kind}
          {item.status === 'suggested' && <span className="ml-2 text-warning">Suggested</span>}
          {item.status === 'superseded' && <span className="ml-2 text-text-muted">Replaced</span>}
        </p>
        <p className="font-mono text-label uppercase text-text-muted" title={item.updated_at ?? item.created_at}>
          {savedAt(item.created_at)}
          {item.updated_at && ` · ${item.status === 'superseded' ? 'replaced' : 'edited'} ${savedAt(item.updated_at)}`}
        </p>
      </div>

      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void save()
          }}
          className="flex flex-col gap-2"
        >
          <label className="sr-only" htmlFor={`edit-${item.id}`}>
            Edit memory
          </label>
          <textarea
            id={`edit-${item.id}`}
            autoFocus
            rows={2}
            maxLength={500}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && (e.stopPropagation(), setEditing(false))}
            className="rounded-input border border-border bg-surface p-2 text-body text-text"
          />
          <div className="flex gap-2">
            <button type="submit" className={`${secondaryButton} bg-voice-assistant text-on-accent hover:border-border`}>
              Save
            </button>
            <button type="button" className={secondaryButton} onClick={() => (setDraft(item.text), setEditing(false))}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <p className={`text-body ${item.status === 'superseded' ? 'text-text-muted line-through' : 'text-text'}`}>
          {item.text}
        </p>
      )}

      <SourceLine item={item} />
      {item.status === 'suggested' && !editing && (
        <div className="flex gap-2">
          <button type="button" className={secondaryButton} onClick={() => void decide('confirmed')}>
            <Icon name="check" className="size-4" />
            Keep
          </button>
          <button type="button" className={secondaryButton} onClick={() => void decide('dismissed')}>
            Dismiss
          </button>
        </div>
      )}
      {failed && (
        <p role="alert" className="text-data text-danger">
          That did not work. Try again.
        </p>
      )}

      {!editing && item.status !== 'superseded' && (
        <div className="-mb-2 -mr-2 flex justify-end gap-1">
          <button type="button" aria-label={`Edit memory: ${item.text}`} className={iconButton} onClick={() => setEditing(true)}>
            <Icon name="edit" className="size-6" />
          </button>
          <button type="button" aria-label={`Delete memory: ${item.text}`} className={iconButton} onClick={() => void remove()}>
            <Icon name="trash" className="size-6" />
          </button>
        </div>
      )}
    </li>
  )
}

const STATUS_LABEL: Partial<Record<ActionItem['status'], string>> = {
  undone: 'Undone',
  failed: 'Failed',
  cancelled: 'Cancelled',
  declined: 'Declined',
  expired: 'Timed out',
}

/** What TalkBack changed, newest first, with Undo (plan P4). */
function Activity({ refreshKey }: { refreshKey?: string }) {
  const { state, reload, set } = useResource(() => api.listActions(), `actions|${refreshKey ?? ''}`)
  const [problem, setProblem] = useState<{ id: string; message: string }>()

  const undo = async (items: ActionItem[], id: string) => {
    setProblem(undefined)
    try {
      const next = await api.undoAction(id)
      set(items.map((a) => (a.id === id ? next : a)))
    } catch (error) {
      setProblem({ id, message: error instanceof ApiError ? error.message : 'That did not work. Try again.' })
    }
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(items) =>
        items.length === 0 ? (
          <p className="text-body text-text-muted">Nothing changed yet. Saves, edits and deletes show up here.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {items.map((action) => (
              <li key={action.id} className="flex flex-col gap-2 rounded-card border border-border bg-bg p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono text-label uppercase text-text-muted">{savedAt(action.created_at)}</p>
                  {STATUS_LABEL[action.status] && (
                    <p className="font-mono text-label uppercase text-text-muted">{STATUS_LABEL[action.status]}</p>
                  )}
                </div>
                <p className={`text-body ${action.status === 'undone' ? 'text-text-muted line-through' : 'text-text'}`}>
                  {action.summary}
                </p>
                {problem?.id === action.id && (
                  <p role="alert" className="text-data text-danger">
                    {problem.message}
                  </p>
                )}
                {action.undoable && (
                  <button
                    type="button"
                    className={`${secondaryButton} self-start`}
                    onClick={() => void undo(items, action.id)}
                    aria-label={`Undo: ${action.summary}`}
                  >
                    <Icon name="retry" className="size-4" />
                    Undo
                  </button>
                )}
              </li>
            ))}
          </ul>
        )
      }
    </ResourceView>
  )
}

/** design.md 5.3. `refreshKey` changes when TalkBack saves or changes memories by voice. */
export function MemoryPanel({ refreshKey }: { refreshKey?: string }) {
  const [tab, setTab] = useState<'memories' | 'activity'>('memories')
  const tabs = useId()
  return (
    <div className="flex min-h-full flex-col gap-4">
      <div role="tablist" aria-label="Memory" className="flex gap-2">
        {(['memories', 'activity'] as const).map((name) => (
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
            {name === 'memories' ? 'Memories' : 'Activity'}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${tabs}-panel`} aria-labelledby={`${tabs}-${tab}`} className="flex flex-1 flex-col">
        {tab === 'memories' ? <Memories refreshKey={refreshKey} /> : <Activity refreshKey={refreshKey} />}
      </div>
    </div>
  )
}

function Memories({ refreshKey }: { refreshKey?: string }) {
  const [history, setHistory] = useState(false)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [confirmAll, setConfirmAll] = useState(false)

  // Wait for a pause in typing before asking the server.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 250)
    return () => clearTimeout(timer)
  }, [query])

  const { state, reload, set } = useResource(
    () => api.listMemories(search, history),
    `${search}|${history}|${refreshKey ?? ''}`,
  )

  const forgetAll = async () => {
    try {
      await api.forgetEverything()
      set([])
    } catch {
      reload()
    }
    setConfirmAll(false)
  }

  return (
    <div className="flex min-h-full flex-col gap-4">
      <div className="relative">
        <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 size-6 -translate-y-1/2 text-text-muted" />
        <label className="sr-only" htmlFor="memory-search">
          Search memories
        </label>
        <input
          id="memory-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search memories"
          className="min-h-target w-full rounded-input border border-border bg-bg pl-12 pr-3 text-body text-text placeholder:text-text-subtle"
        />
      </div>
      <SettingsToggleRow
        label="Show replaced memories"
        description="Older versions that a correction replaced. TalkBack no longer uses them."
        checked={history}
        onChange={setHistory}
      />

      <ResourceView state={state} onRetry={reload}>
        {(items) =>
          items.length === 0 ? (
            <div className="flex flex-col gap-2">
              <p className="text-body text-text">{search ? 'No memories match.' : 'Nothing remembered yet.'}</p>
              {!search && (
                <p className="text-body text-text-muted">
                  Try: <span className="text-voice-user">“Remember that I prefer Celsius.”</span>
                </p>
              )}
            </div>
          ) : (
            <>
              <ul className="flex flex-col gap-3">
                {items.map((item) => (
                  <MemoryCard
                    key={item.id}
                    item={item}
                    onSaved={(next) => set(items.map((m) => (m.id === next.id ? next : m)))}
                    onDeleted={(id) => set(items.filter((m) => m.id !== id))}
                  />
                ))}
              </ul>
              <div className="mt-auto pt-4">
                {confirmAll ? (
                  <div role="alertdialog" aria-label="Forget everything" className="flex flex-col gap-3 rounded-card border border-danger p-4">
                    <p className="text-body text-text">Delete all memories? You can undo this from Activity.</p>
                    <div className="flex gap-2">
                      <button type="button" onClick={() => void forgetAll()} className={`${secondaryButton} border-danger text-danger`}>
                        Yes, forget everything
                      </button>
                      <button type="button" onClick={() => setConfirmAll(false)} className={secondaryButton}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button type="button" onClick={() => setConfirmAll(true)} className={`${secondaryButton} w-full border-danger text-danger`}>
                    Forget everything
                  </button>
                )}
              </div>
            </>
          )
        }
      </ResourceView>
    </div>
  )
}
