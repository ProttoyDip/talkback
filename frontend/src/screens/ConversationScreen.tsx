import { AnimatePresence, motion } from 'motion/react'
import { type RefObject, useCallback, useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from 'react'
import { DATA_CHANGED, api } from '../api/client'
import { Icon } from '../components/Icon'
import { downloadTranscript } from '../state/exportTranscript'
import { enter, exit } from '../styles/motion'
import { Banner, type BannerProps } from '../components/Banner'
import { ConfirmCard } from '../components/ConfirmCard'
import { FlowBackground } from '../components/FlowBackground'
import { PresenceOrb } from '../components/PresenceOrb'
import type { LevelMeters } from '../session/useLevelHistory'
import { Drawer } from '../components/Drawer'
import { Toast, type ToastData } from '../components/Toast'
import type { ConversationModel, Remembered } from '../session/model'
import { MicButton, type MicMode } from '../components/MicButton'
import { NavRail, TabBar, type Panel } from '../components/Navigation'
import { StatusBar } from '../components/StatusBar'
import { ReminderBanner } from '../components/ReminderBanner'
import { TextComposer } from '../components/TextComposer'
import type { DueReminder } from '../session/useReminders'
import { TranscriptTurn } from '../components/TranscriptTurn'
import type { ConfirmRequest, ConversationState, TimelineData, ToolName, Turn } from '../state/types'

/** Everything the Conversation screen shows. Live, replay and preview all build this. */
export interface ConversationView {
  state: ConversationState
  tool?: ToolName
  turns: Turn[]
  confirm?: ConfirmRequest
  banner?: BannerProps
  timeline: TimelineData
  /** Mic input level, 0..1. */
  inputLevel: number
  micMode: MicMode
  micDisabled: boolean
  latencyMs?: number
  /** Set while a backup model answers, e.g. "Planner: nemotron via OpenRouter". */
  backup?: string
  /** Last memory TalkBack saved; shows the "Remembered" toast with Undo. */
  remembered?: Remembered
  /** Bumped when stored data changes by voice (data.changed): open panels reload. */
  dataVersion?: number
  /** True once the session is open, so skills can run. */
  sessionOpen?: boolean
  /** The recorded demo (?replay): labelled everywhere, panels show sample data. */
  replay?: boolean
  /** Due or missed reminders (plan P5), until the user answers each. */
  reminders?: DueReminder[]
  onDismissReminder?: (id: string) => void
  /** Set while the opt-in recording runs: downloads it as a WAV file. */
  onSaveRecording?: () => void
  activeModels?: ConversationModel['models']
  /** Live voice levels, so the presence orb can pulse with them. */
  levels?: RefObject<LevelMeters>
}

interface ConversationScreenProps {
  view: ConversationView
  debug: boolean
  onToggleMute: () => void
  onAnswerConfirm: (approved: boolean) => void
  /** Stop TalkBack talking now (Esc or the Stop button). */
  onStop?: () => void
  /** Push-to-talk is on: hold Space or the mic button to talk. */
  onHold?: (held: boolean) => void
  /** An example chip on the empty screen was chosen: send its words as a typed turn. */
  onExample?: (text: string) => void
  /** Typed turns (plan P3); missing in the recorded demo. */
  onSendText?: (text: string) => void
}

/** First-conversation guidance: what to try, and the words to say. */
const EXAMPLES = [
  { label: 'Remember a preference', say: 'Remember that I like short answers.' },
  { label: 'Research a topic', say: 'Quick research on solar batteries.' },
  { label: 'Prepare my day', say: 'Morning brief.' },
]

function isTyping(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  )
}

/** Within this distance of the bottom, new captions keep the view pinned. */
const FOLLOW_THRESHOLD_PX = 160

/** TalkBack is answering, so Stop has something to stop. */
const STOPPABLE = new Set(['assistant_speaking', 'overlap', 'thinking', 'tool'])

export function ConversationScreen({
  view,
  debug,
  onToggleMute,
  onAnswerConfirm,
  onStop,
  onHold,
  onExample,
  onSendText,
}: ConversationScreenProps) {
  const [panel, setPanel] = useState<Panel | null>(null)
  // Undo from a chip or toast changes data without data.changed: reload panels.
  const [localVersion, setLocalVersion] = useState(0)
  useEffect(() => {
    const bump = () => setLocalVersion((v) => v + 1)
    window.addEventListener(DATA_CHANGED, bump)
    return () => window.removeEventListener(DATA_CHANGED, bump)
  }, [])
  const [example, setExample] = useState<string>()
  const { state, turns, confirm, micDisabled } = view
  // Nothing said yet: the orb holds the centre of the stage.
  const empty = turns.length === 0 && !confirm
  const canStop = onStop !== undefined && STOPPABLE.has(state)

  // Live captions follow the newest words, unless the user scrolled up to read.
  const transcriptRef = useRef<HTMLElement>(null)
  const following = useRef(true)
  useLayoutEffect(() => {
    const el = transcriptRef.current
    if (el && following.current) el.scrollTop = el.scrollHeight
  }, [turns, confirm])

  // Toasts: a new memory shows "Remembered" with Undo for 4 s (design.md 11).
  const [toast, setToast] = useState<ToastData | null>(null)
  const dismissToast = useCallback(() => setToast(null), [])
  const [seenMemory, setSeenMemory] = useState(view.remembered?.id)
  if (view.remembered && view.remembered.id !== seenMemory) {
    const { id, text, suggested, actionId, replacedText } = view.remembered
    setSeenMemory(id)
    setToast(
      suggested
        ? {
            id,
            message: `Suggested: ${text}`,
            action: { label: 'Keep', onClick: () => void api.editMemory(id, { status: 'confirmed' }).catch(() => {}) },
          }
        : {
            id,
            message: replacedText ? `Remembered: ${text} (instead of ${replacedText})` : `Remembered: ${text}`,
            action: {
              label: 'Undo',
              // Through the action history, so a correction puts the old memory back.
              onClick: () => void (actionId ? api.undoAction(actionId) : api.deleteMemory(id)).catch(() => {}),
            },
          },
    )
  }

  const togglePanel = (next: Panel) => setPanel((cur) => (cur === next ? null : next))

  // Keyboard shortcuts from design.md 7: Space mute, M memory, K skills, Esc close.
  const toggleMute = useEffectEvent(onToggleMute)
  const holdToTalk = useEffectEvent((held: boolean) => onHold?.(held))
  const pushToTalk = onHold !== undefined && view.micMode !== 'off'
  // Esc closes an open panel first; otherwise it stops TalkBack (design.md 7).
  const escape = useEffectEvent(() => {
    if (panel) setPanel(null)
    else if (canStop) onStop?.()
  })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return
      const onButton = e.target instanceof HTMLElement && e.target.closest('button, a, [tabindex]')
      if (e.code === 'Space' && !onButton && !micDisabled) {
        e.preventDefault()
        if (!pushToTalk) toggleMute()
        else if (!e.repeat) holdToTalk(true)
      } else if (e.key === 'm' || e.key === 'M') {
        togglePanel('memory')
      } else if (e.key === 'p' || e.key === 'P') {
        togglePanel('plan')
      } else if (e.key === 'k' || e.key === 'K') {
        togglePanel('skills')
      } else if (e.key === ',') {
        togglePanel('settings')
      } else if (e.key === 'Escape') {
        escape()
      }
    }
    const onKeyUp = (e: KeyboardEvent) => {
      if (pushToTalk && e.code === 'Space' && !isTyping(e.target)) holdToTalk(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [micDisabled, pushToTalk])

  const mic = (
    <MicButton
      mode={view.micMode}
      level={view.inputLevel}
      disabled={micDisabled}
      onToggle={onToggleMute}
      onHold={onHold}
    />
  )

  return (
    <div className="flex min-h-dvh">
      <FlowBackground state={state} />
      <NavRail openPanel={panel} onTogglePanel={togglePanel} />

      <main className="flex min-w-0 flex-1 justify-center">
        <div className="flex h-dvh w-full max-w-stage flex-col gap-6 px-4 pt-6 sm:px-8 lg:pt-8">
          <StatusBar
            state={state}
            tool={view.tool}
            debug={debug}
            latencyMs={view.latencyMs}
            backup={view.backup}
            replay={view.replay}
            connected={view.sessionOpen}
            onSaveRecording={view.onSaveRecording}
            onSave={turns.length > 0 ? () => downloadTranscript(turns) : undefined}
          />

          {view.banner && <Banner {...view.banner} />}
          {view.reminders && view.onDismissReminder && (
            <ReminderBanner due={view.reminders} onDismiss={view.onDismissReminder} />
          )}

          {/* TalkBack's presence: a 3D orb in the middle of the stage. It reacts
              when you speak and when TalkBack answers. Before the first words it
              sits in the centre with the invitation under it. */}
          <div
            className={
              empty
                ? `flex flex-1 flex-col items-center justify-center gap-8 lg:pb-0 ${
                    onSendText ? '' : 'pb-[calc(var(--mic-size)+var(--space-12))]'
                  }`
                : 'flex shrink-0 flex-col items-center gap-4'
            }
          >
            <PresenceOrb
              state={state}
              levels={view.levels}
              compact={!empty}
              latest={{ user: view.timeline.user.at(-1) ?? 0, assistant: view.timeline.assistant.at(-1) ?? 0 }}
            />
            <AnimatePresence>
              {canStop && (
                <motion.button
                  key="stop"
                  type="button"
                  onClick={onStop}
                  aria-keyshortcuts="Escape"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0, transition: enter }}
                  exit={{ opacity: 0, transition: exit }}
                  className="inline-flex min-h-target items-center gap-2 rounded-pill border border-field-line bg-chrome px-4 font-medium text-text transition-colors duration-(--dur-fast) hover:border-text-subtle active:scale-[0.97]"
                >
                  <Icon name="stop" className="size-4" />
                  Stop
                  <span className="font-mono text-label uppercase text-text-muted">Esc</span>
                </motion.button>
              )}
            </AnimatePresence>
            {empty && (
              <div className="flex flex-col items-center gap-2 text-center">
                <p className="font-display text-h1 font-extrabold text-text">Interrupt me any time.</p>
                <p className="text-transcript text-text-muted">I'll keep up.</p>
              </div>
            )}
            {empty && !view.replay && (
              <div className="flex flex-col items-center gap-3">
                <p id="examples-label" className="font-mono text-label uppercase text-text-muted">
                  Try saying
                </p>
                <ul aria-labelledby="examples-label" className="flex flex-wrap justify-center gap-2">
                  {EXAMPLES.map(({ label, say }) => (
                    <li key={label}>
                      <button
                        type="button"
                        aria-pressed={example === say}
                        onClick={() => {
                          setExample(say)
                          onExample?.(say)
                        }}
                        className="min-h-target rounded-pill border border-field-line bg-chrome px-4 text-body text-text transition-colors duration-(--dur-fast) hover:border-text-subtle aria-pressed:border-voice-assistant"
                      >
                        {label}
                      </button>
                    </li>
                  ))}
                </ul>
                {/* Live, a chip sends its words; the static preview shows them instead. */}
                {!onExample && (
                  <p aria-live="polite" className="min-h-target text-transcript text-text-muted">
                    {example && <>Say: “{example}”</>}
                  </p>
                )}
              </div>
            )}
          </div>

          {!empty && (
            <section
              ref={transcriptRef}
              aria-label="Transcript"
              onScroll={(e) => {
                const el = e.currentTarget
                following.current = el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD_PX
              }}
              // The translucent panel keeps captions readable where the field passes behind them.
              className={`-mx-4 flex-1 overflow-y-auto rounded-panel bg-bg/80 px-4 sm:-mx-8 sm:px-8 lg:pb-8 ${
                onSendText ? 'pb-4' : 'pb-[calc(var(--mic-size)+var(--space-12))]'
              }`}
            >
              {view.replay && (
                <p className="pt-2 font-mono text-label uppercase text-text-muted">
                  Sample conversation. Nothing here is live.
                </p>
              )}
              <ol className="grid grid-cols-1 gap-4 py-2 sm:grid-cols-[max-content_minmax(0,1fr)] sm:gap-x-6">
                {turns.map((turn, i) => (
                  // A user turn opens a new exchange: more space before it,
                  // so each question sits close to its answer.
                  <TranscriptTurn
                    key={turn.id}
                    turn={turn}
                    startsExchange={turn.speaker === 'user' && turns[i - 1]?.speaker !== 'user'}
                  />
                ))}
              </ol>

              <AnimatePresence>
                {confirm && state !== 'offline' && (
                  <ConfirmCard key={confirm.callId} className="mt-8" request={confirm} onAnswer={onAnswerConfirm} />
                )}
              </AnimatePresence>
            </section>
          )}

          {/* The bottom row: typing, and on desktop the mic beside it. On
              phones the mic lives in the tab bar, so the row clears its
              raised button. */}
          <div
            className={`flex items-end justify-center gap-6 lg:pb-8 ${
              onSendText ? 'pb-[calc(var(--mic-size)+var(--space-4))]' : 'hidden lg:flex'
            }`}
          >
            {onSendText && (
              <div className="min-w-0 flex-1">
                <TextComposer onSend={onSendText} disabled={state === 'offline'} />
              </div>
            )}
            <div className="hidden lg:block">{mic}</div>
          </div>
        </div>
      </main>

      <AnimatePresence>
        {panel && (
          <Drawer
            key={panel}
            panel={panel}
            onClose={() => setPanel(null)}
            context={{
              memoryVersion: `${view.remembered?.id ?? ''}|${view.dataVersion ?? 0}|${localVersion}`,
              sessionOpen: view.sessionOpen ?? false,
              replay: view.replay ?? false,
              onSkillRan: (name) => setToast({ id: `skill-${name}-${Date.now()}`, message: `Running ${name}` }),
              activeModels: view.activeModels ?? {},
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>{toast && <Toast key={toast.id} toast={toast} onDismiss={dismissToast} />}</AnimatePresence>

      <TabBar openPanel={panel} onTogglePanel={togglePanel} mic={mic} />
    </div>
  )
}
