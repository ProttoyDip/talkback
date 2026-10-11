import { useState } from 'react'
import { ApiError, api } from '../../api/client'
import { useResource } from '../../api/useResource'
import { Icon } from '../Icon'
import type { SkillItem } from '../../api/types'
import { SkillForm } from './SkillForm'
import { iconButton, ResourceView, secondaryButton } from './shared'
import { TOOL_LABEL } from './toolLabels'


/** The live app: the same page without ?replay. */
const LIVE_HREF = window.location.pathname

/** design.md 5.4. A skill runs inside the live conversation, so it needs one. */
export function SkillsPanel({
  sessionOpen,
  replay = false,
  onRan,
}: {
  sessionOpen: boolean
  /** The recorded demo: skills are shown, but only a live conversation can run them. */
  replay?: boolean
  onRan: (name: string) => void
}) {
  const { state, reload, set } = useResource(() => api.listSkills(), 'skills')
  // Your own skills (plan P5): a form for new, edited or copied skills.
  const [form, setForm] = useState<{ edit?: SkillItem; copy?: SkillItem } | null>(null)
  const [problem, setProblem] = useState<string>()

  const toggle = async (skills: SkillItem[], skill: SkillItem) => {
    try {
      const next = await api.updateSkill(skill.id, { enabled: !(skill.enabled ?? true) })
      set(skills.map((s) => (s.id === next.id ? next : s)))
    } catch {
      setProblem("That change was not saved. Try again.")
    }
  }

  const remove = async (skills: SkillItem[], skill: SkillItem) => {
    try {
      await api.deleteSkill(skill.id)
      set(skills.filter((s) => s.id !== skill.id))
    } catch {
      setProblem("That skill was not deleted. Try again.")
    }
  }
  const [running, setRunning] = useState<string>()
  const [failed, setFailed] = useState<{ id: string; message: string }>()

  const run = async (id: string, name: string) => {
    setRunning(id)
    setFailed(undefined)
    try {
      await api.runSkill(id)
      onRan(name)
    } catch (error) {
      // 409: the server has no live conversation for this browser.
      const noSession = error instanceof ApiError && error.status === 409
      setFailed({ id, message: noSession ? 'Start the conversation to run a skill.' : "Couldn't start this skill. Try again." })
    }
    setRunning(undefined)
  }

  return (
    <ResourceView state={state} onRetry={reload}>
      {(skills) =>
        skills.length === 0 ? (
          <div className="flex flex-col gap-2">
            <p className="text-body text-text">No skills yet.</p>
            <p className="text-body text-text-muted">
              Skills like <span className="font-mono text-data text-text">morning brief</span> appear here once they
              are added.
            </p>
          </div>
        ) : (
          <>
            {replay ? (
              <p className="mb-4 flex flex-wrap items-center gap-x-2 text-data text-text-muted">
                Skills run in a live conversation.
                <a href={LIVE_HREF} className="text-voice-assistant underline underline-offset-4">
                  Start a live conversation
                </a>
              </p>
            ) : (
              !sessionOpen && <p className="mb-4 text-data text-text-muted">Start the conversation to run a skill.</p>
            )}
            {!replay &&
              (form ? (
                <div className="mb-4">
                  <SkillForm
                    skill={form.edit}
                    copyOf={form.copy}
                    onCancel={() => setForm(null)}
                    onSaved={(saved) => {
                      set(skills.some((s) => s.id === saved.id) ? skills.map((s) => (s.id === saved.id ? saved : s)) : [...skills, saved])
                      setForm(null)
                    }}
                  />
                </div>
              ) : (
                <button type="button" onClick={() => setForm({})} className={`${secondaryButton} mb-4 self-start`}>
                  <Icon name="skills" className="size-4" />
                  Make your own skill
                </button>
              ))}
            {problem && (
              <p role="alert" className="mb-4 text-data text-danger">
                {problem}
              </p>
            )}
            <ul className="flex flex-col gap-3">
              {skills.map((skill) => (
                <li
                  key={skill.id}
                  className={`flex flex-col gap-3 rounded-card border border-border bg-bg p-4 ${skill.enabled === false ? 'opacity-70' : ''}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-display text-h2 font-bold">
                      {skill.name}
                      {skill.builtin === false && (
                        <span className="ml-2 align-middle font-mono text-label uppercase text-voice-user">Yours</span>
                      )}
                      {skill.enabled === false && (
                        <span className="ml-2 align-middle font-mono text-label uppercase text-text-muted">Off</span>
                      )}
                    </h3>
                    {!replay && skill.builtin === false && (
                      <span className="-mr-2 -mt-2 flex">
                        <button type="button" className={iconButton} aria-label={`Edit skill: ${skill.name}`} onClick={() => setForm({ edit: skill })}>
                          <Icon name="edit" className="size-6" />
                        </button>
                        <button type="button" className={iconButton} aria-label={`Delete skill: ${skill.name}`} onClick={() => void remove(skills, skill)}>
                          <Icon name="trash" className="size-6" />
                        </button>
                      </span>
                    )}
                  </div>
                  {skill.summary && <p className="text-body text-text-muted">{skill.summary}</p>}
                  <ul aria-label="Say" className="flex flex-wrap gap-2">
                    {skill.triggers.map((trigger) => (
                      <li key={trigger} className="rounded-input border border-border px-2 font-mono text-data text-text-muted">
                        {trigger}
                      </li>
                    ))}
                  </ul>
                  <ul aria-label="Allowed tools" className="flex flex-wrap gap-3 text-text-muted">
                    {skill.allowed_tools.map((tool) => (
                      <li key={tool} className="flex items-center gap-1 text-data">
                        <Icon name={TOOL_LABEL[tool].icon} className="size-4" />
                        {TOOL_LABEL[tool].label}
                      </li>
                    ))}
                  </ul>
                  {failed?.id === skill.id && (
                    <p role="alert" className="text-data text-danger">
                      {failed.message}
                    </p>
                  )}
                  {!replay && (
                    <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!sessionOpen || running === skill.id || skill.enabled === false}
                      onClick={() => void run(skill.id, skill.name)}
                      className={`${secondaryButton} self-start`}
                    >
                      <Icon name="play" className="size-4" />
                      {running === skill.id ? 'Starting…' : `Run ${skill.name}`}
                    </button>
                    {skill.builtin === false ? (
                      <button type="button" onClick={() => void toggle(skills, skill)} className={secondaryButton}>
                        {skill.enabled === false ? 'Turn on' : 'Turn off'}
                      </button>
                    ) : (
                      <button type="button" onClick={() => setForm({ copy: skill })} className={secondaryButton}>
                        Make a copy
                      </button>
                    )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </>
        )
      }
    </ResourceView>
  )
}
