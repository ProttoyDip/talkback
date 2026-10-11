import type { ToolName } from '../../session/protocol'
import type { IconName } from '../Icon'

/** Plain names for tools, shared by Skills and Settings. */
export const TOOL_LABEL: Record<ToolName, { icon: IconName; label: string }> = {
  weather: { icon: 'weather', label: 'Weather' },
  web_search: { icon: 'globe', label: 'Web search' },
  memory_read: { icon: 'memory', label: 'Read saved memories' },
  memory_write: { icon: 'memory', label: 'Save memories' },
  memory_delete: { icon: 'memory', label: 'Delete saved memories' },
  memory_suggest: { icon: 'memory', label: 'Suggest memories' },
  skill_run: { icon: 'skills', label: 'Skills' },
  task_list: { icon: 'task', label: 'Read tasks' },
  task_add: { icon: 'task', label: 'Add tasks' },
  task_update: { icon: 'task', label: 'Change tasks' },
  task_delete: { icon: 'task', label: 'Delete tasks' },
  calendar_list: { icon: 'calendar', label: 'Read the calendar' },
  calendar_add: { icon: 'calendar', label: 'Add calendar blocks' },
  calendar_update: { icon: 'calendar', label: 'Move calendar blocks' },
  calendar_delete: { icon: 'calendar', label: 'Delete calendar blocks' },
  reminder_set: { icon: 'bell', label: 'Set reminders' },
  reminder_update: { icon: 'bell', label: 'Change reminders' },
  day_plan_propose: { icon: 'calendar', label: 'Plan your day' },
  day_plan_apply: { icon: 'calendar', label: 'Apply a day plan' },
}
