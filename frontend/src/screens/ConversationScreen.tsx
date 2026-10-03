import { AnimatePresence } from 'motion/react'
import { type RefObject, useCallback, useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { Banner, type BannerProps } from '../components/Banner'
import { ConfirmCard } from '../components/ConfirmCard'
import { PresenceOrb } from '../components/PresenceOrb'
import type { LevelMeters } from '../session/useLevelHistory'
import { Drawer } from '../components/Drawer'
import { Toast, type ToastData } from '../components/Toast'
import type { ConversationModel } from '../session/model'
import { MicButton, type MicMode } from '../components/MicButton'
import { NavRail, TabBar, type Panel } from '../components/Navigation'
import { StatusBar } from '../components/StatusBar'
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
  remembered?: { id: string; text: string }
  /** True once the session is open, so skills can run. */
  sessionOpen?: boolean
  activeModels?: ConversationModel['models']
  /** Live voice levels, so the presence orb can pulse with them. */
  levels?: RefObject<LevelMeters>
}

interface ConversationScreenProps {
  view: ConversationView
  debug: boolean
  onToggleMute: () => void
  onAnswerConfirm: (approved: boolean) => void
}

function isTyping(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  )
}

/** Within this distance of the bottom, new captions keep the view pinned. */
const FOLLOW_THRESHOLD_PX = 160

export function ConversationScreen({ view, debug, onToggleMute, onAnswerConfirm }: ConversationScreenProps) {
  const [panel, setPanel] = useState<Panel | null>(null)
  const { state, turns, confirm, micDisabled } = view
  // Nothing said yet: the orb holds the centre of the stage.
  const empty = turns.length === 0 && !confirm

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
    const { id, text } = view.remembered
    setSeenMemory(id)
    setToast({
      id,
      message: `Remembered: ${text}`,
      action: { label: 'Undo', onClick: () => void api.deleteMemory(id).catch(() => {}) },
    })
  }

  const togglePanel = (next: Panel) => setPanel((cur) => (cur === next ? null : next))

  // Keyboard shortcuts from design.md 7: Space mute, M memory, K skills, Esc close.
  const toggleMute = useEffectEvent(onToggleMute)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return
      const onButton = e.target instanceof HTMLElement && e.target.closest('button, a, [tabindex]')
      if (e.code === 'Space' && !onButton && !micDisabled) {
        e.preventDefault()
        toggleMute()
      } else if (e.key === 'm' || e.key === 'M') {
        togglePanel('memory')
      } else if (e.key === 'k' || e.key === 'K') {
        togglePanel('skills')
      } else if (e.key === ',') {
        togglePanel('settings')
      } else if (e.key === 'Escape') {
        setPanel(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [micDisabled])

  const mic = (
    <MicButton
      mode={view.micMode}
      level={view.inputLevel}
      disabled={micDisabled}
      onToggle={onToggleMute}
    />
  )

  return (
    <div className="flex min-h-dvh">
      <NavRail openPanel={panel} onTogglePanel={togglePanel} />

      <main className="flex min-w-0 flex-1 justify-center">
        <div className="flex h-dvh w-full max-w-stage flex-col gap-6 px-4 pt-6 sm:px-8 lg:pt-8">
          <StatusBar
            state={state}
            tool={view.tool}
            debug={debug}
            latencyMs={view.latencyMs}
            backup={view.backup}
          />

          {view.banner && <Banner {...view.banner} />}

          {/* TalkBack's presence: a 3D orb in the middle of the stage. It reacts
              when you speak and when TalkBack answers. Before the first words it
              sits in the centre with the invitation under it. */}
          <div
            className={
              empty
                ? 'flex flex-1 flex-col items-center justify-center gap-8 pb-[calc(var(--mic-size)+var(--space-12))] lg:pb-0'
                : 'flex shrink-0 justify-center'
            }
          >
            <PresenceOrb
              state={state}
              levels={view.levels}
              compact={!empty}
              latest={{ user: view.timeline.user.at(-1) ?? 0, assistant: view.timeline.assistant.at(-1) ?? 0 }}
            />
            {empty && (
              <div className="flex flex-col items-center gap-2 text-center">
                <p className="font-display text-h1 font-extrabold text-text">Interrupt me any time.</p>
                <p className="text-transcript text-text-muted">I'll keep up.</p>
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
              className="-mx-4 flex-1 overflow-y-auto px-4 pb-[calc(var(--mic-size)+var(--space-12))] sm:-mx-8 sm:px-8 lg:pb-8"
            >
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

          <div className="hidden justify-center pb-8 lg:flex">{mic}</div>
        </div>
      </main>

      <AnimatePresence>
        {panel && (
          <Drawer
            key={panel}
            panel={panel}
            onClose={() => setPanel(null)}
            context={{
              memoryVersion: view.remembered?.id,
              sessionOpen: view.sessionOpen ?? false,
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
