import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, api } from '../../api/client'
import type { DocumentItem, ProjectDetail, ProjectItem } from '../../api/types'
import { useResource } from '../../api/useResource'
import { when } from '../../state/when'
import { Icon } from '../Icon'
import { iconButton, ResourceView, secondaryButton } from './shared'

const card = 'flex items-start gap-3 rounded-card border border-border bg-bg p-4'
const field = 'min-h-target rounded-input border border-border bg-bg px-3 text-body text-text'
const ACCEPT = '.pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown'

function Problem({ message }: { message?: string }) {
  return message ? (
    <p role="alert" className="text-data text-danger">
      {message}
    </p>
  ) : null
}

function size(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function meta(doc: DocumentItem) {
  const pages = doc.pages ? ` · ${doc.pages} ${doc.pages === 1 ? 'page' : 'pages'}` : ''
  return `${doc.kind.toUpperCase()}${pages} · ${size(doc.size_bytes)}`
}

/**
 * Documents (plan P8): files TalkBack can search and quote when asked. Their
 * text is information, never instructions. Reading and indexing finish after
 * the upload, so the list checks again while any file is still being read.
 */
export function Documents({ refreshKey }: { refreshKey?: string }) {
  const { state, reload, set } = useResource(api.listDocuments, `documents|${refreshKey ?? ''}`)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string>()
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const hint = useId()
  const items = state.status === 'ready' ? state.data : undefined
  const reading = items?.some((d) => d.status === 'processing') ?? false

  useEffect(() => {
    if (!reading) return
    const timer = window.setTimeout(() => {
      api.listDocuments().then(set, () => {})
    }, 2000)
    return () => window.clearTimeout(timer)
  }, [reading, items, set])

  const add = async (files: FileList | null) => {
    const file = files?.[0]
    if (!file || !items) return
    setBusy(true)
    setProblem(undefined)
    try {
      const doc = await api.uploadDocument(file)
      set([doc, ...items])
    } catch (error) {
      setProblem(error instanceof ApiError && error.status !== 0 ? error.message : 'Could not reach the server. Try again.')
    }
    setBusy(false)
    if (input.current) input.current.value = ''
  }

  const remove = async (doc: DocumentItem) => {
    if (!items) return
    try {
      await api.deleteDocument(doc.id)
      set(items.filter((d) => d.id !== doc.id))
    } catch {
      setProblem(`Couldn't delete “${doc.title}”. Try again.`)
    }
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(docs) => (
        <div className="flex flex-col gap-4">
          <label
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              void add(e.dataTransfer.files)
            }}
            className={`flex cursor-pointer flex-col items-center gap-2 rounded-card border border-dashed px-4 py-6 text-center transition-colors duration-(--dur-fast) focus-within:border-voice-assistant ${
              dragging ? 'border-voice-assistant bg-surface-raised' : 'border-border hover:border-text-subtle'
            }`}
          >
            <Icon name="document" className="size-6 text-voice-assistant" />
            <span className="text-body font-medium text-text">{busy ? 'Adding…' : 'Add a document'}</span>
            <span id={hint} className="text-data text-text-muted">
              PDF, TXT or Markdown, up to 5 MB and 50 pages. Drop it here or choose a file.
            </span>
            <input
              ref={input}
              type="file"
              accept={ACCEPT}
              aria-describedby={hint}
              disabled={busy}
              onChange={(e) => void add(e.target.files)}
              className="sr-only"
            />
          </label>
          <Problem message={problem} />
          {docs.length === 0 ? (
            <p className="text-body text-text-muted">
              No documents yet. Add one, then ask{' '}
              <span className="text-voice-user">“What does my lease say about pets?”</span>
            </p>
          ) : (
            <ul className="flex flex-col gap-2" aria-label="Your documents">
              {docs.map((doc) => (
                <li key={doc.id} className={card}>
                  <Icon name="document" className="mt-1 size-4 shrink-0 text-text-muted" />
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-body text-text">{doc.title}</p>
                    {doc.status === 'processing' && (
                      <p role="status" className="text-data text-text-muted">
                        Reading… You can ask about it in a moment.
                      </p>
                    )}
                    {doc.status === 'failed' && (
                      <p className="text-data text-danger">Couldn't add it. {doc.error ?? 'Try another file.'}</p>
                    )}
                    {doc.status === 'ready' && <p className="text-data text-text-muted">{meta(doc)}</p>}
                  </div>
                  <button
                    type="button"
                    className={iconButton}
                    aria-label={`Delete document: ${doc.title}`}
                    onClick={() => void remove(doc)}
                  >
                    <Icon name="trash" className="size-6" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="text-data text-text-muted">
            TalkBack reads your documents as information only: it quotes them and never follows instructions inside them.
          </p>
        </div>
      )}
    </ResourceView>
  )
}

/** One project's notes, with the web pages they came from. */
function ProjectNotes({ project, onChanged }: { project: ProjectItem; onChanged: () => void }) {
  const { state, reload, set } = useResource(() => api.getProject(project.id), `project|${project.id}|${project.notes}`)
  const [problem, setProblem] = useState<string>()

  const removeNote = async (detail: ProjectDetail, id: string) => {
    try {
      await api.deleteNote(project.id, id)
      set({ ...detail, notes: detail.notes.filter((n) => n.id !== id) })
      onChanged()
    } catch {
      setProblem("Couldn't delete the note. Try again.")
    }
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(detail) => (
        <div className="flex flex-col gap-2">
          <Problem message={problem} />
          {detail.notes.length === 0 ? (
            <p className="text-data text-text-muted">
              No notes yet. Try saying <span className="text-voice-user">“Save that to {project.name}.”</span>
            </p>
          ) : (
            <ul className="flex flex-col gap-2" aria-label={`Notes in ${project.name}`}>
              {detail.notes.map((note) => (
                <li key={note.id} className="flex items-start gap-2 border-l-2 border-border pl-3">
                  <div className="min-w-0 flex-1">
                    <p className="whitespace-pre-line break-words text-body text-text">{note.text}</p>
                    <p className="text-data text-text-muted">{when(note.created_at)}</p>
                    {note.sources.length > 0 && (
                      <ul className="flex flex-col">
                        {note.sources.map((s) => (
                          <li key={s.url}>
                            <a
                              href={s.url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="inline-flex min-h-target items-center gap-2 text-data text-text-muted underline decoration-border underline-offset-4 hover:text-text"
                            >
                              {s.title}
                              <Icon name="external" className="size-4 shrink-0" />
                              <span className="sr-only">(opens in a new tab)</span>
                            </a>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <button
                    type="button"
                    className={iconButton}
                    aria-label="Delete this note"
                    onClick={() => void removeNote(detail, note.id)}
                  >
                    <Icon name="trash" className="size-6" />
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

/** Research projects (plan P8): notes saved by voice, each with its sources. */
export function Projects({ refreshKey }: { refreshKey?: string }) {
  const { state, reload, set } = useResource(api.listProjects, `projects|${refreshKey ?? ''}`)
  const [name, setName] = useState('')
  const [open, setOpen] = useState<string>()
  const [confirming, setConfirming] = useState<string>()
  const [problem, setProblem] = useState<string>()
  const id = useId()

  const create = async (items: ProjectItem[]) => {
    const value = name.trim()
    if (!value) return
    try {
      const project = await api.createProject(value)
      set([project, ...items])
      setName('')
      setProblem(undefined)
      setOpen(project.id)
    } catch (error) {
      setProblem(error instanceof ApiError && error.status === 409 ? error.message : 'That did not work. Try again.')
    }
  }

  const remove = async (items: ProjectItem[], project: ProjectItem) => {
    try {
      await api.deleteProject(project.id)
      set(items.filter((p) => p.id !== project.id))
      setConfirming(undefined)
    } catch {
      setProblem(`Couldn't delete “${project.name}”. Try again.`)
    }
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(items) => (
        <div className="flex flex-col gap-4">
          <form
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              void create(items)
            }}
          >
            <label htmlFor={`${id}-name`} className="text-body font-medium text-text">
              New project
            </label>
            <div className="flex gap-2">
              <input
                id={`${id}-name`}
                value={name}
                maxLength={100}
                onChange={(e) => setName(e.target.value)}
                className={`${field} min-w-0 flex-1`}
              />
              <button type="submit" disabled={!name.trim()} className={secondaryButton}>
                Create
              </button>
            </div>
            <Problem message={problem} />
          </form>
          {items.length === 0 ? (
            <p className="text-body text-text-muted">
              No projects yet. Try saying{' '}
              <span className="text-voice-user">
                “Look up heat pumps and save the key points to a project called Home.”
              </span>
            </p>
          ) : (
            <ul className="flex flex-col gap-2" aria-label="Your projects">
              {items.map((project) => {
                const expanded = open === project.id
                return (
                  <li key={project.id} className="flex flex-col gap-3 rounded-card border border-border bg-bg p-4">
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-controls={`${id}-${project.id}`}
                        onClick={() => setOpen(expanded ? undefined : project.id)}
                        className="flex min-h-target min-w-0 flex-1 items-center gap-3 text-left"
                      >
                        <Icon name="folder" className="size-4 shrink-0 text-voice-assistant" />
                        <span className="min-w-0 flex-1">
                          <span className="block break-words text-body text-text">{project.name}</span>
                          <span className="block text-data text-text-muted">
                            {project.notes === 1 ? '1 note' : `${project.notes} notes`}
                          </span>
                        </span>
                        <Icon
                          name="chevron"
                          className={`size-4 shrink-0 text-text-muted transition-transform duration-(--dur-fast) ${expanded ? 'rotate-180' : ''}`}
                        />
                      </button>
                      <button
                        type="button"
                        className={iconButton}
                        aria-label={`Delete project: ${project.name}`}
                        onClick={() => setConfirming(project.id)}
                      >
                        <Icon name="trash" className="size-6" />
                      </button>
                    </div>
                    {confirming === project.id && (
                      <div role="alert" className="flex flex-wrap items-center gap-3">
                        <p className="text-data text-text">Delete “{project.name}” and its notes? This can't be undone.</p>
                        <button
                          type="button"
                          onClick={() => void remove(items, project)}
                          className="min-h-target rounded-pill border border-danger px-4 font-medium text-danger"
                        >
                          Delete
                        </button>
                        <button type="button" onClick={() => setConfirming(undefined)} className={secondaryButton}>
                          Keep it
                        </button>
                      </div>
                    )}
                    {expanded && (
                      <div id={`${id}-${project.id}`}>
                        <ProjectNotes
                          project={project}
                          onChanged={() =>
                            set(items.map((p) => (p.id === project.id ? { ...p, notes: Math.max(0, p.notes - 1) } : p)))
                          }
                        />
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </ResourceView>
  )
}
