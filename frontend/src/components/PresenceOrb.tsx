import { useEffect, useRef, type RefObject } from 'react'
import type { OrbMood, StormOrb } from '../background/stormOrb'
import type { LevelMeters } from '../session/useLevelHistory'
import type { ConversationState } from '../state/types'
import { sceneDisabled } from './sceneSupport'

/*
 * What the orb does in each state. Listening and speaking pulse with the
 * live voice, thinking swirls faster, an interruption bursts, offline and
 * muted dim it. The status label next to it says the same in words.
 */
const MOODS: Record<ConversationState, OrbMood & { voice: 'user' | 'assistant' | 'both' | 'none' }> = {
  idle: { dive: 0.05, pulse: 0, presence: 0.85, voice: 'none' },
  listening: { dive: 0.2, pulse: 1, presence: 1, voice: 'user' },
  thinking: { dive: 0.55, pulse: 0, presence: 1, voice: 'none' },
  tool: { dive: 0.55, pulse: 0, presence: 1, voice: 'none' },
  assistant_speaking: { dive: 0.25, pulse: 1, presence: 1, voice: 'assistant' },
  overlap: { dive: 0.3, pulse: 1, presence: 1, voice: 'both' },
  interrupted: { dive: 0.1, pulse: 0, presence: 1, voice: 'none' },
  confirm: { dive: 0.1, pulse: 0, presence: 0.9, voice: 'none' },
  muted: { dive: 0, pulse: 0, presence: 0.45, voice: 'none' },
  offline: { dive: 0, pulse: 0, presence: 0.2, voice: 'none' },
}

interface PresenceOrbProps {
  state: ConversationState
  /** Live levels from mic capture and playback; missing in the design preview. */
  levels?: RefObject<LevelMeters>
  /** Number of interruptions so far; each new one makes the orb burst. */
  interrupts?: number
  /** Latest voice levels (0..1), exposed for tests as data attributes. */
  latest?: { user: number; assistant: number }
}

/** TalkBack's presence: the Storm orb at the top of the stage reacts to the conversation. */
export function PresenceOrb({ state, levels, interrupts = 0, latest }: PresenceOrbProps) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const orb = useRef<StormOrb | null>(null)
  const mood = useRef(MOODS[state])

  useEffect(() => {
    const element = canvas.current
    if (!element || sceneDisabled()) return
    let cancelled = false
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const level = () => {
      const meters = levels?.current
      if (!meters) return 0
      switch (mood.current.voice) {
        case 'user':
          return meters.user
        case 'assistant':
          return meters.assistant
        case 'both':
          return Math.max(meters.user, meters.assistant)
        default:
          return 0
      }
    }
    void import('../background/stormOrb').then(({ createStormOrb }) => {
      if (cancelled) return
      orb.current = createStormOrb(element, level, still)
      orb.current?.setMood(mood.current)
    })
    return () => {
      cancelled = true
      orb.current?.dispose()
      orb.current = null
    }
  }, [levels])

  useEffect(() => {
    mood.current = MOODS[state]
    orb.current?.setMood(MOODS[state])
  }, [state])

  useEffect(() => {
    if (interrupts > 0) orb.current?.burst()
  }, [interrupts])

  return (
    <div
      aria-hidden
      data-voice-user={latest?.user.toFixed(3)}
      data-voice-assistant={latest?.assistant.toFixed(3)}
      className="relative size-orb shrink-0 rounded-pill bg-orb-bg [mask-image:radial-gradient(circle,#000_56%,transparent_71%)] lg:size-orb-lg"
    >
      <canvas ref={canvas} className="block size-full rounded-pill" />
    </div>
  )
}
