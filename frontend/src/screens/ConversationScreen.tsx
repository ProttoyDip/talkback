import { AnimatePresence } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { ConfirmCard } from '../components/ConfirmCard'
import { Drawer } from '../components/Drawer'
import { DuplexTimeline } from '../components/DuplexTimeline'
import { MicButton, type MicMode } from '../components/MicButton'
import { NavRail, TabBar, type Panel } from '../components/Navigation'
import { OfflineBanner } from '../components/OfflineBanner'
import { StatusBar } from '../components/StatusBar'
import { TranscriptTurn } from '../components/TranscriptTurn'
import {
  placeholderConfirm,
  placeholderInputLevel,
  placeholderTimeline,
  placeholderToolTurn,
  placeholderTurns,
} from '../state/placeholder'
import type { ConversationState } from '../state/types'

interface ConversationScreenProps {
  /** Preview state, from `?state=` until the session drives it. */
  initialState: ConversationState
  debug: boolean
}

function isTyping(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  )
}

export function ConversationScreen({ initialState, debug }: ConversationScreenProps) {
  const [muted, setMuted] = useState(initialState === 'muted')
  const [panel, setPanel] = useState<Panel | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(initialState === 'confirm')

  const offline = initialState === 'offline'
  const state: ConversationState = offline
    ? 'offline'
    : muted
      ? 'muted'
      : initialState === 'muted'
        ? 'idle'
        : initialState === 'confirm' && !confirmOpen
          ? 'assistant_speaking'
          : initialState

  const turns =
    state === 'idle'
      ? []
      : state === 'tool' || state === 'thinking'
        ? [...placeholderTurns, placeholderToolTurn]
        : placeholderTurns

  const micMode: MicMode = muted ? 'muted' : 'live'
  const listening = state === 'listening' || state === 'overlap'
  const level = listening ? placeholderInputLevel : 0

  // Live captions follow the newest words, like a caption track.
  const transcriptRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const el = transcriptRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns.length, confirmOpen])

  const togglePanel = (next: Panel) => setPanel((cur) => (cur === next ? null : next))

  // Keyboard shortcuts from design.md 7: Space mute, M memory, K skills, Esc close.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return
      const onButton = e.target instanceof HTMLElement && e.target.closest('button, a, [tabindex]')
      if (e.code === 'Space' && !onButton && !offline) {
        e.preventDefault()
        setMuted((m) => !m)
      } else if (e.key === 'm' || e.key === 'M') {
        togglePanel('memory')
      } else if (e.key === 'k' || e.key === 'K') {
        togglePanel('skills')
      } else if (e.key === 'Escape') {
        setPanel(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [offline])

  const mic = (
    <MicButton
      mode={micMode}
      level={level}
      disabled={offline}
      onToggle={() => setMuted((m) => !m)}
    />
  )

  return (
    <div className="flex min-h-dvh">
      <NavRail openPanel={panel} onTogglePanel={togglePanel} />

      <main className="flex min-w-0 flex-1 justify-center">
        <div className="flex h-dvh w-full max-w-stage flex-col gap-6 px-4 pt-6 sm:px-8 lg:pt-8">
          <StatusBar state={state} tool={state === 'tool' ? 'weather' : undefined} debug={debug} />

          {offline && <OfflineBanner onRetry={() => {}} />}

          <DuplexTimeline data={placeholderTimeline} state={state} />

          <section
            ref={transcriptRef}
            aria-label="Transcript"
            className="-mx-4 flex-1 overflow-y-auto px-4 pb-[calc(var(--mic-size)+var(--space-12))] sm:-mx-8 sm:px-8 lg:pb-8"
          >
            {turns.length === 0 ? (
              <div className="flex h-full flex-col items-start justify-center gap-2 py-12">
                <p className="font-display text-h1 font-extrabold text-text">
                  Interrupt me any time.
                </p>
                <p className="text-transcript text-text-muted">I'll keep up.</p>
              </div>
            ) : (
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
            )}

            <AnimatePresence>
              {confirmOpen && !offline && (
                <ConfirmCard
                  className="mt-8"
                  request={placeholderConfirm}
                  onAnswer={() => setConfirmOpen(false)}
                />
              )}
            </AnimatePresence>
          </section>

          <div className="hidden justify-center pb-8 lg:flex">{mic}</div>
        </div>
      </main>

      <AnimatePresence>
        {panel && <Drawer key={panel} panel={panel} onClose={() => setPanel(null)} />}
      </AnimatePresence>

      <TabBar openPanel={panel} onTogglePanel={togglePanel} mic={mic} />
    </div>
  )
}
