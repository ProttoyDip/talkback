import { useState } from 'react'
import { api } from '../../api/client'
import { useResource } from '../../api/useResource'
import type { ToolName } from '../../session/protocol'
import { Icon, type IconName } from '../Icon'
import { ResourceView, secondaryButton } from './shared'

const TOOL_LABEL: Record<ToolName, { icon: IconName; label: string }> = {
  weather: { icon: 'weather', label: 'Weather' },
  web_search: { icon: 'globe', label: 'Web search' },
  memory_read: { icon: 'memory', label: 'Read memory' },
  memory_write: { icon: 'memory', label: 'Save memory' },
  memory_delete: { icon: 'memory', label: 'Delete memory' },
  skill_run: { icon: 'skills', label: 'Skills' },
}

/** design.md 5.4. A skill runs inside the live conversation, so it needs one. */
export function SkillsPanel({ sessionOpen, onRan }: { sessionOpen: boolean; onRan: (name: string) => void }) {
  const { state, reload } = useResource(() => api.listSkills(), 'skills')
  const [running, setRunning] = useState<string>()
  const [failed, setFailed] = useState<string>()

  const run = async (id: string, name: string) => {
    setRunning(id)
    setFailed(undefined)
    try {
      await api.runSkill(id)
      onRan(name)
    } catch {
      setFailed(id)
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
            {!sessionOpen && (
              <p className="mb-4 text-data text-text-muted">Start the conversation to run a skill.</p>
            )}
            <ul className="flex flex-col gap-3">
              {skills.map((skill) => (
                <li key={skill.id} className="flex flex-col gap-3 rounded-card border border-border bg-bg p-4">
                  <h3 className="font-display text-h2 font-bold">{skill.name}</h3>
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
                  {failed === skill.id && (
                    <p role="alert" className="text-data text-danger">
                      Could not start this skill. Try again.
                    </p>
                  )}
                  <button
                    type="button"
                    disabled={!sessionOpen || running === skill.id}
                    onClick={() => void run(skill.id, skill.name)}
                    className={`${secondaryButton} self-start`}
                  >
                    <Icon name="play" className="size-4" />
                    {running === skill.id ? 'Starting…' : `Run ${skill.name}`}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )
      }
    </ResourceView>
  )
}
