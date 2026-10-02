import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { MemoryItem } from '../../api/types'
import { useResource } from '../../api/useResource'
import { Icon } from '../Icon'
import { iconButton, ResourceView, secondaryButton } from './shared'

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
        <p className="font-mono text-label font-medium uppercase text-voice-user">{item.kind}</p>
        <p className="font-mono text-label uppercase text-text-muted">{savedAt(item.created_at)}</p>
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
        <p className="text-body text-text">{item.text}</p>
      )}

      {item.utterance && (
        <p className="text-data text-text-muted">
          You said: <span className="text-text">“{item.utterance}”</span>
        </p>
      )}
      {failed && (
        <p role="alert" className="text-data text-danger">
          That did not work. Try again.
        </p>
      )}

      {!editing && (
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

/** design.md 5.3. `refreshKey` changes when TalkBack saves a new memory. */
export function MemoryPanel({ refreshKey }: { refreshKey?: string }) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [confirmAll, setConfirmAll] = useState(false)

  // Wait for a pause in typing before asking the server.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 250)
    return () => clearTimeout(timer)
  }, [query])

  const { state, reload, set } = useResource(() => api.listMemories(search), `${search}|${refreshKey ?? ''}`)

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
                    <p className="text-body text-text">Delete all memories? This cannot be undone.</p>
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
