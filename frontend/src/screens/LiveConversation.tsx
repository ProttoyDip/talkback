import { useEffect, useMemo, useRef, useState } from 'react'
import { AudioEngine, MIC_PROBLEM_COPY, MicError, type MicProblem } from '../audio/engine'
import type { BannerProps } from '../components/Banner'
import type { MicMode } from '../components/MicButton'
import type { ConversationModel } from '../session/model'
import { toTurns } from '../session/model'
import { PROVIDER_NAMES } from '../session/protocol'
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
    return { tone: 'danger', message: model.error.message, action: { label: 'Retry now', onClick: reconnect } }
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

/** "Planner: <model> via <provider>" for the first role served by a backup. */
function backupLabel(model: ConversationModel): string | undefined {
  for (const role of ['voice', 'planner', 'search'] as const) {
    const active = model.models[role]
    if (active?.backup) {
      const name = role[0].toUpperCase() + role.slice(1)
      return `${name}: ${active.model} via ${PROVIDER_NAMES[active.provider]}`
    }
  }
  return undefined
}

/** The real conversation: server events (live) or the demo fixture (replay). */
export function LiveConversation({
  mode,
  debug,
  replaySpeed = 1,
}: {
  mode: SessionMode
  debug: boolean
  replaySpeed?: number
}) {
  const session = useSession(mode, replaySpeed)
  const { model, started, muted, setMuted, answerConfirm, reconnect } = session

  // Mic capture (F2) and playback (F3) write here; the timeline samples it.
  const meters = useRef<LevelMeters>({ user: 0, assistant: 0 })
  const timeline = useLevelHistory(meters, model.interrupts)

  const engineRef = useRef<AudioEngine | null>(null)
  const [starting, setStarting] = useState(false)
  const [micProblem, setMicProblem] = useState<MicProblem | null>(null)

  useEffect(() => () => void engineRef.current?.close(), [])

  /** Runs on the user's click or key press (browsers require a gesture for audio). */
  const begin = async () => {
    if (starting || started) return
    setStarting(true)
    setMicProblem(null)
    const engine = new AudioEngine({
      onFrame: (frame) => session.sendAudio(frame),
      onInputLevel: (level) => (meters.current.user = level),
      onOutputLevel: (level) => (meters.current.assistant = level),
      onPosition: (seq, samplesPlayed) =>
        session.send({ type: 'playback.position', seq, samples_played: samplesPlayed }),
    })
    try {
      await engine.start()
      // The replay does not listen, so it never asks for the microphone.
      if (mode === 'live') await engine.startMic()
    } catch (error) {
      await engine.close()
      setMicProblem(error instanceof MicError ? error.problem : 'unavailable')
      setStarting(false)
      return
    }
    engineRef.current = engine
    session.attachAudio(
      (seq, pcm) => engine.enqueue(seq, pcm),
      (event) => {
        if (event.type === 'audio.flush') engine.flush()
      },
    )
    session.start()
    setStarting(false)
  }

  const toggleMute = () => {
    if (!started) {
      void begin()
      return
    }
    engineRef.current?.setMuted(!muted)
    setMuted(!muted)
  }

  const turns = useMemo(() => toTurns(model), [model])
  const state = displayState(model, muted)
  const micMode: MicMode = !started ? 'off' : muted ? 'muted' : 'live'

  const banner: BannerProps | undefined = micProblem
    ? { tone: 'danger', message: MIC_PROBLEM_COPY[micProblem], action: { label: 'Try again', onClick: () => void begin() } }
    : bannerFor(model, reconnect)

  const view: ConversationView = {
    state,
    tool: state === 'tool' ? model.tool : undefined,
    turns,
    confirm: model.confirm,
    banner,
    timeline,
    // The newest sample of the user lane is the current input level.
    inputLevel: timeline.user.at(-1) ?? 0,
    micMode,
    micDisabled: state === 'offline' || starting,
    latencyMs: model.latencyMs,
    backup: backupLabel(model),
  }

  return (
    <ConversationScreen view={view} debug={debug} onToggleMute={toggleMute} onAnswerConfirm={answerConfirm} />
  )
}
