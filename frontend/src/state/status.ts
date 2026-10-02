import type { ConversationState, ToolName } from './types'

export const TOOL_STATUS_NAME: Record<ToolName, string> = {
  weather: 'WEATHER',
  web_search: 'THE WEB',
  memory_read: 'MEMORY',
  memory_write: 'MEMORY',
  memory_delete: 'MEMORY',
  skill_run: 'SKILL',
}

/** Status labels from docs/design.md, section 6. */
export function statusLabel(state: ConversationState, tool?: ToolName): string {
  switch (state) {
    case 'idle':
      return 'READY'
    case 'listening':
      return 'LISTENING'
    case 'assistant_speaking':
      return 'TALKBACK SPEAKING'
    case 'overlap':
      return 'BOTH SPEAKING'
    case 'interrupted':
      return 'YOU INTERRUPTED'
    case 'thinking':
      return 'THINKING'
    case 'tool':
      return `CHECKING ${tool ? TOOL_STATUS_NAME[tool] : ''}`.trim()
    case 'confirm':
      return 'NEEDS YOUR OK'
    case 'muted':
      return 'MUTED'
    case 'offline':
      return 'OFFLINE'
  }
}

/** Plain-language text for screen readers (the waveform is aria-hidden). */
export function statusDescription(state: ConversationState): string {
  switch (state) {
    case 'idle':
      return 'Ready. Start talking.'
    case 'listening':
      return 'Listening to you.'
    case 'assistant_speaking':
      return 'TalkBack is speaking. You can interrupt.'
    case 'overlap':
      return 'You and TalkBack are both speaking.'
    case 'interrupted':
      return 'You interrupted. TalkBack stopped.'
    case 'thinking':
      return 'TalkBack is thinking.'
    case 'tool':
      return 'TalkBack is checking something.'
    case 'confirm':
      return 'TalkBack needs your OK.'
    case 'muted':
      return 'Microphone muted.'
    case 'offline':
      return 'The voice engine is offline.'
  }
}
