import { useId, useState } from 'react'
import { ApiError, api } from '../../api/client'
import type { SkillCreate, SkillItem } from '../../api/types'
import type { ToolName } from '../../session/protocol'
import { secondaryButton } from './shared'
import { TOOL_LABEL } from './toolLabels'

/** Tools a skill may use (backend skills.SKILL_TOOLS). */
const SKILL_TOOLS: ToolName[] = [
  'weather', 'web_search', 'memory_read', 'memory_suggest',
  'task_list', 'task_add', 'task_update', 'calendar_list', 'calendar_add', 'calendar_update', 'reminder_set',
]
const MAX_INSTRUCTIONS = 2000
const field = 'min-h-target rounded-input border border-border bg-bg px-3 text-body text-text'

/** Make or edit your own skill (plan P5). `skill` set: edit; otherwise new (optionally copied). */
export function SkillForm({
  skill,
  copyOf,
  onSaved,
  onCancel,
}: {
  skill?: SkillItem
  copyOf?: SkillItem
  onSaved: (skill: SkillItem) => void
  onCancel: () => void
}) {
  const start = skill ?? copyOf
  const [name, setName] = useState(skill ? skill.name : copyOf ? `${copyOf.name} (mine)` : '')
  const [phrases, setPhrases] = useState(skill ? skill.triggers.join(', ') : '')
  const [tools, setTools] = useState<ToolName[]>(start?.allowed_tools.filter((t) => SKILL_TOOLS.includes(t)) ?? [])
  const [instructions, setInstructions] = useState(skill?.instructions ?? copyOf?.summary ?? '')
  const [problem, setProblem] = useState<string>()
  const [saving, setSaving] = useState(false)
  const id = useId()

  const save = async () => {
    const triggers = phrases.split(',').map((p) => p.trim()).filter(Boolean)
    if (!name.trim() || triggers.length === 0 || !instructions.trim()) {
      setProblem('Add a name, at least one phrase, and what TalkBack should do.')
      return
    }
    const body: SkillCreate = { name: name.trim(), triggers, allowed_tools: tools, instructions: instructions.trim() }
    setSaving(true)
    try {
      onSaved(skill ? await api.updateSkill(skill.id, body) : await api.createSkill(body))
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : 'That did not work. Try again.')
    }
    setSaving(false)
  }

  return (
    <form
      aria-label={skill ? `Edit ${skill.name}` : 'New skill'}
      className="flex flex-col gap-3 rounded-card border border-voice-assistant bg-bg p-4"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <label htmlFor={`${id}-name`} className="text-body font-medium text-text">
        Name
      </label>
      <input id={`${id}-name`} value={name} maxLength={60} onChange={(e) => setName(e.target.value)} className={field} />

      <label htmlFor={`${id}-say`} className="text-body font-medium text-text">
        Say
      </label>
      <input
        id={`${id}-say`}
        value={phrases}
        onChange={(e) => setPhrases(e.target.value)}
        aria-describedby={`${id}-say-help`}
        className={field}
      />
      <p id={`${id}-say-help`} className="text-data text-text-muted">
        Phrases that start it, separated by commas, like “wrap up my day”.
      </p>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-body font-medium text-text">It may use</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {SKILL_TOOLS.map((tool) => (
            <label key={tool} className="flex min-h-target items-center gap-2 text-data text-text">
              <input
                type="checkbox"
                checked={tools.includes(tool)}
                onChange={(e) => setTools((list) => (e.target.checked ? [...list, tool] : list.filter((t) => t !== tool)))}
                className="size-4 accent-(--voice-assistant)"
              />
              {TOOL_LABEL[tool].label}
            </label>
          ))}
        </div>
      </fieldset>

      <label htmlFor={`${id}-do`} className="text-body font-medium text-text">
        What TalkBack does
      </label>
      <textarea
        id={`${id}-do`}
        rows={4}
        maxLength={MAX_INSTRUCTIONS}
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
        aria-describedby={`${id}-count`}
        className="rounded-input border border-border bg-bg p-2 text-body text-text"
      />
      <p id={`${id}-count`} className="self-end font-mono text-label text-text-muted">
        {instructions.length} / {MAX_INSTRUCTIONS}
      </p>

      {problem && (
        <p role="alert" className="text-data text-danger">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className={`${secondaryButton} bg-voice-assistant text-on-accent hover:border-border`}>
          {saving ? 'Saving…' : skill ? 'Save' : 'Make skill'}
        </button>
        <button type="button" onClick={onCancel} className={secondaryButton}>
          Cancel
        </button>
      </div>
    </form>
  )
}
