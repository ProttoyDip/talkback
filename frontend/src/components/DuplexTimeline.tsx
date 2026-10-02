import { motion } from 'motion/react'
import { useEffect, useRef } from 'react'
import type { ConversationState, TimelineData } from '../state/types'
import { dur } from '../styles/motion'

interface DuplexTimelineProps {
  data: TimelineData
  state: ConversationState
}

type LaneTone = 'user' | 'assistant' | 'offline'

/** Below this level a slot is drawn as a quiet baseline dash. */
const SILENCE = 0.05
/** Narrowest slot in CSS px. Levels are merged when the lane is narrower. */
const MIN_SLOT = 6

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Merge levels into `slots` buckets, keeping the peak of each bucket. */
function bucket(levels: number[], slots: number) {
  if (slots >= levels.length) return levels
  const out: number[] = []
  const size = levels.length / slots
  for (let s = 0; s < slots; s++) {
    let peak = 0
    for (let i = Math.floor(s * size); i < Math.floor((s + 1) * size); i++) {
      peak = Math.max(peak, levels[i] ?? 0)
    }
    out.push(peak)
  }
  return out
}

function Lane({
  levels,
  tone,
  label,
  row,
}: {
  levels: number[]
  tone: LaneTone
  label: string
  row: 1 | 2
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const color = cssVar(
      tone === 'user' ? '--voice-user' : tone === 'assistant' ? '--voice-assistant' : '--border',
    )

    const draw = () => {
      const { width, height } = canvas.getBoundingClientRect()
      if (width === 0 || height === 0) return
      const dpr = window.devicePixelRatio || 1
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      ctx.fillStyle = color

      const values = bucket(levels, Math.max(1, Math.floor(width / MIN_SLOT)))
      const slot = width / values.length
      const barWidth = Math.max(2, Math.min(8, slot * 0.55))
      const mid = height / 2

      values.forEach((level, i) => {
        const x = i * slot + (slot - barWidth) / 2
        if (level < SILENCE) {
          // Silence: a short dash on the centre line, like the cover image.
          const dash = Math.min(barWidth * 1.4, slot * 0.6)
          ctx.beginPath()
          ctx.roundRect(i * slot + (slot - dash) / 2, mid - 1.5, dash, 3, 1.5)
          ctx.fill()
          return
        }
        const h = Math.max(barWidth, level * height)
        ctx.beginPath()
        ctx.roundRect(x, mid - h / 2, barWidth, h, barWidth / 2)
        ctx.fill()
      })
    }

    draw()
    const observer = new ResizeObserver(draw)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [levels, tone])

  const labelColor =
    tone === 'user' ? 'text-voice-user' : tone === 'assistant' ? 'text-voice-assistant' : 'text-text-subtle'

  return (
    <>
      <span
        className={`col-start-1 font-mono text-label font-medium uppercase ${labelColor} ${ROW[row]}`}
      >
        {label}
      </span>
      <canvas ref={canvasRef} className={`col-start-2 block h-12 w-full min-w-0 ${ROW[row]}`} />
    </>
  )
}

const FLAT: number[] = []
const ROW = { 1: 'row-start-1', 2: 'row-start-2' } as const

/**
 * Two lanes, YOU and TALKBACK, over the last ~10 seconds (design.md 5.2).
 * Static placeholder levels for now; real levels come from the AudioWorklet.
 * Decorative for assistive tech: the status bar carries the text equivalent.
 */
export function DuplexTimeline({ data, state }: DuplexTimelineProps) {
  const offline = state === 'offline'
  const flat = state === 'idle' || offline
  const hideUser = state === 'muted'
  const showInterrupts = !flat

  const userLevels = flat ? FLAT : data.user
  const assistantLevels = flat ? FLAT : data.assistant
  const emptyLane = Array.from({ length: data.user.length }, () => 0)

  return (
    <section
      aria-hidden
      className="relative rounded-panel border border-border bg-surface px-4 py-6 sm:px-6"
    >
      <div className="grid grid-cols-[max-content_minmax(0,1fr)] items-center gap-x-4 gap-y-4 sm:gap-x-6">
        {hideUser ? (
          <>
            <span className="col-start-1 row-start-1 font-mono text-label font-medium uppercase text-text-subtle">
              You
            </span>
            <p className="col-start-2 row-start-1 flex h-12 items-center font-mono text-label uppercase text-text-subtle">
              Mic muted
            </p>
          </>
        ) : (
          <Lane
            row={1}
            label="You"
            tone={offline ? 'offline' : 'user'}
            levels={userLevels.length ? userLevels : emptyLane}
          />
        )}
        <Lane
          row={2}
          label="TalkBack"
          tone={offline ? 'offline' : 'assistant'}
          levels={assistantLevels.length ? assistantLevels : emptyLane}
        />

        {showInterrupts && (
          // Tick marks sit over the lane column only (second grid column).
          <div className="pointer-events-none relative col-start-2 row-start-1 row-end-3 h-full">
            {data.interrupts.map((seconds) => (
              <motion.div
                key={seconds}
                className="absolute inset-y-0 flex flex-col items-center"
                style={{ left: `${(seconds / data.windowSeconds) * 100}%` }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: dur.fast }}
              >
                <span className="-translate-x-1/2 absolute bottom-[calc(100%+var(--space-1))] rounded-pill bg-text px-2 font-mono text-label text-bg">
                  interrupt
                </span>
                <span className="-translate-x-1/2 absolute inset-y-0 border-l border-dashed border-text" />
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
