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
}
