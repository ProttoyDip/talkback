import { useMemo, useRef } from 'react'
import type { BannerProps } from '../components/Banner'
import type { ConversationModel } from '../session/model'
import { toTurns } from '../session/model'
import { useLevelHistory, type LevelMeters } from '../session/useLevelHistory'
import { useSession, type SessionMode } from '../session/useSession'
import type { ConversationState } from '../state/types'
import { ConversationScreen, type ConversationView } from './ConversationScreen'

/** Copy from design.md 5.6: plain, specific, with a next step. */
function bannerFor(model: ConversationModel, reconnect: () => void): BannerProps | undefined {
  if (model.connection === 'reconnecting') {
    return { tone: 'danger', message: 'Connection lost. Reconnecting… your transcript is safe.' }
  }
  if (model.ended === 'idle') {
    return {
      tone: 'neutral',
      message: 'The session ended after 2 minutes of silence.',
      action: { label: 'Start again', onClick: reconnect },
    }
  }
  if (model.ended === 'time_limit') {
    return {
      tone: 'neutral',
      message: 'The session reached its 30-minute limit.',
      action: { label: 'Start again', onClick: reconnect },
    }
  }
  if (model.connection === 'closed') {
    return { tone: 'neutral', message: 'The session has ended.', action: { label: 'Start again', onClick: reconnect } }
  }
  if (model.error?.code === 'voice_engine_offline') {
    return {
      tone: 'danger',
      message: model.error.message,
      action: { label: 'Retry now', onClick: reconnect },
    }
  }
  if (model.error) return { tone: 'danger', message: model.error.message }
  return undefined
}

function displayState(model: ConversationModel, muted: boolean): ConversationState {
  if (model.connection === 'reconnecting' || model.connection === 'closed') return 'offline'
  if (model.error?.code === 'voice_engine_offline') return 'offline'
  if (muted) return 'muted'
  // The confirm card stays until the user answers, whatever the server state.
  if (model.confirm) return 'confirm'
  return model.state === 'muted' ? 'idle' : model.state
}

/** The real conversation: server events (live) or the demo fixture (replay). */
export function LiveConversation({ mode, debug }: { mode: SessionMode; debug: boolean }) {
  const { model, muted, setMuted, answerConfirm, reconnect } = useSession(mode)

  // Filled by mic capture (F2) and playback (F3). Until then the lanes stay quiet.
  const meters = useRef<LevelMeters>({ user: 0, assistant: 0 })
  const timeline = useLevelHistory(meters, model.interrupts)

  const turns = useMemo(() => toTurns(model), [model])
  const state = displayState(model, muted)

  const view: ConversationView = {
    state,
    tool: state === 'tool' ? model.tool : undefined,
    turns,
    confirm: model.confirm,
    banner: bannerFor(model, reconnect),
    timeline,
    // The newest sample of the user lane is the current input level.
    inputLevel: timeline.user.at(-1) ?? 0,
    muted,
    micDisabled: state === 'offline',
    latencyMs: model.latencyMs,
  }

  return (
    <ConversationScreen
      view={view}
      debug={debug}
      onToggleMute={() => setMuted(!muted)}
      onAnswerConfirm={answerConfirm}
    />
  )
}
