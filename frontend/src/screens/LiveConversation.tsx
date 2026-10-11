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
import { authConfig } from '../api/auth'
import { AccessCodeError, SignInRequiredError, requestSession } from '../api/session'
import { useEffectsSetting } from '../background/effects'
import { api, rememberSessionToken } from '../api/client'
import { useReminders } from '../session/useReminders'
import { downloadBlob } from '../state/exportTranscript'
import { AccessGate } from './AccessGate'
import { SignIn } from './SignIn'
import { hasOnboarded } from './onboarded'
import { Onboarding } from './Onboarding'
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

  const effects = useEffectsSetting()
  const engineRef = useRef<AudioEngine | null>(null)
  const [starting, setStarting] = useState(false)
  const [micProblem, setMicProblem] = useState<MicProblem | null>(null)
  const [micSilent, setMicSilent] = useState(false)
  const [recording, setRecording] = useState(false)
  // First run: onboarding (design.md 5.1). The replay needs none.
  const [onboarding, setOnboarding] = useState(() => mode === 'live' && !hasOnboarded())
  const [tip, setTip] = useState(false)
  // Public demo gate (SECURITY.md T8): ask once whether this browser may start a session.
  // With accounts on (plan P2), the sign-in screen replaces the code-only gate.
  const [access, setAccess] = useState<'checking' | 'open' | 'locked' | 'signin'>(
    mode === 'live' ? 'checking' : 'open',
  )
  const [needsCode, setNeedsCode] = useState(false)
  useEffect(() => {
    if (access !== 'checking') return
    void authConfig().then((config) => {
      setNeedsCode(config.access_code)
      const accounts = config.mode !== 'off'
      return requestSession().then(
        (body) => {
          rememberSessionToken(body.token, body.expires_at)
          setAccess('open')
        },
        (error: unknown) => {
          if (error instanceof SignInRequiredError) setAccess('signin')
          else if (error instanceof AccessCodeError) setAccess(accounts ? 'signin' : 'locked')
          else setAccess('open') // any other failure is shown by the connection banner later
        },
      )
    })
  }, [access])

  useEffect(() => () => void engineRef.current?.close(), [])

  // Reminders while the page is open (plan P5), and the user's time zone, so
  // "tomorrow at 3" means their 3 PM.
  const reminders = useReminders(mode === 'live' && access === 'open', model.reminders)
  useEffect(() => {
    if (mode !== 'live' || access !== 'open') return
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone
    api
      .getSettings()
      .then((settings) => (zone && settings.timezone !== zone ? api.updateSettings({ timezone: zone }) : undefined))
      .catch(() => {})
  }, [mode, access])

  // Typing can start a conversation without the microphone (plan P3).
  const [micOn, setMicOn] = useState(false)
  const pendingText = useRef<string | null>(null)

  const openMic = async (engine: AudioEngine) => {
    await engine.startMic()
    setMicOn(true)
    // Opt-in recording (Settings > Privacy), chosen in this browser: never uploaded.
    if (effects.saveRecordings) {
      engine.startRecording()
      setRecording(true)
    }
  }

  /** Runs on the user's click or key press (browsers require a gesture for audio). */
  const begin = async (withMic = true) => {
    if (starting || started) return
    setStarting(true)
    setMicProblem(null)
    setMicSilent(false)
    const engine = new AudioEngine({
      onFrame: (frame) => session.sendAudio(frame),
      onInputLevel: (level) => (meters.current.user = level),
      onSilentMic: setMicSilent,
      onOutputLevel: (level) => (meters.current.assistant = level),
      onPosition: (seq, samplesPlayed) =>
        session.send({ type: 'playback.position', seq, samples_played: samplesPlayed }),
    })
    try {
      await engine.start()
      // The replay does not listen, so it never asks for the microphone.
      if (mode === 'live' && withMic) await openMic(engine)
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

  const setMicMuted = (next: boolean) => {
    engineRef.current?.setMuted(next)
    setMuted(next)
  }

  /** The conversation started by typing; now the user wants to talk too. */
  const startMicLater = async () => {
    const engine = engineRef.current
    if (!engine || micOn) return
    setMicProblem(null)
    try {
      await openMic(engine)
    } catch (error) {
      setMicProblem(error instanceof MicError ? error.problem : 'unavailable')
    }
  }

  /** A typed turn; starts the conversation (without the mic) if needed. */
  const sendText = (text: string) => {
    if (mode !== 'live') return
    if (started && model.connection === 'open') {
      session.sendText(text)
      return
    }
    pendingText.current = text
    if (!started) void begin(false)
  }
  useEffect(() => {
    if (model.connection !== 'open' || !pendingText.current) return
    session.sendText(pendingText.current)
    pendingText.current = null
  }, [model.connection, session])

  const toggleMute = () => {
    if (!started) {
      void begin()
      return
    }
    if (!micOn) {
      void startMicLater()
      return
    }
    setMicMuted(!muted)
  }

  // Push-to-talk (Settings > On this device): muted until Space or the mic is held.
  const { pushToTalk } = effects
  useEffect(() => {
    if (started && pushToTalk) {
      engineRef.current?.setMuted(true)
      setMuted(true)
    }
  }, [started, pushToTalk, setMuted])
  const hold = (held: boolean) => {
    if (!started) {
      if (held) void begin()
      return
    }
    if (!micOn) {
      if (held) void startMicLater()
      return
    }
    if (muted === !held) return
    setMicMuted(!held)
  }

  const turns = useMemo(() => toTurns(model), [model])
  const state = displayState(model, muted)
  // A conversation started by typing has no mic yet: the button offers to start it.
  const micMode: MicMode = !started || (mode === 'live' && !micOn) ? 'off' : muted ? 'muted' : 'live'

  const banner: BannerProps | undefined = micProblem
    ? { tone: 'danger', message: MIC_PROBLEM_COPY[micProblem], action: { label: 'Try again', onClick: () => void (started ? startMicLater() : begin()) } }
    : (bannerFor(model, reconnect) ??
      (micSilent && !muted ? { tone: 'danger' as const, message: MIC_PROBLEM_COPY.silent } : undefined) ??
      (tip
        ? {
            tone: 'neutral' as const,
            message: 'Use headphones for the best interruptions.',
            action: { label: 'Got it', icon: 'check' as const, onClick: () => setTip(false) },
          }
        : undefined))

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
    remembered: model.remembered,
    dataVersion: model.dataVersion,
    sessionOpen: model.connection === 'open',
    replay: mode === 'replay',
    reminders: reminders.due,
    plan: model.plan,
    resumable: model.resumable,
    onResume: (stateId, accept) => session.send({ type: 'session.resume', state_id: stateId, accept }),
    onDismissReminder: reminders.dismiss,
    onSaveRecording: recording
      ? () => {
          const wav = engineRef.current?.recording()
          if (wav) downloadBlob(wav, 'wav')
        }
      : undefined,
    activeModels: model.models,
    levels: meters,
  }

  if (access === 'locked') return <AccessGate onPass={() => setAccess('open')} />
  if (access === 'signin') return <SignIn needsCode={needsCode} onPass={() => setAccess('checking')} />
  if (access === 'checking') return null

  if (onboarding) {
    return (
      <Onboarding
        onStart={() => {
          setOnboarding(false)
          setTip(true)
          void begin()
        }}
        onLater={() => setOnboarding(false)}
      />
    )
  }

  return (
    <ConversationScreen
      view={view}
      debug={debug}
      onToggleMute={toggleMute}
      onAnswerConfirm={answerConfirm}
      onStop={session.stop}
      onHold={pushToTalk ? hold : undefined}
      onExample={sendText}
      onSendText={mode === 'live' ? sendText : undefined}
    />
  )
}
