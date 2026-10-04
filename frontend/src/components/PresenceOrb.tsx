import { useEffect, useRef, type RefObject } from 'react'
import type { OrbMood, StormOrb } from '../background/stormOrb'
import type { LevelMeters } from '../session/useLevelHistory'
import type { ConversationState } from '../state/types'
import { useEffectsSetting } from '../background/effects'
import { sceneDisabled } from './sceneSupport'

/*
 * The orb reacts to two things only: the user speaking (listening) and
 * TalkBack answering. Everything else leaves it at rest; muted and offline
 * dim it. The status label next to the wordmark says the state in words.
 */
type Mood = OrbMood & { voice: 'user' | 'assistant' | 'both' | 'none' }
const REST: Mood = { dive: 0, pulse: 0, presence: 0.9, voice: 'none' }
const MOODS: Record<ConversationState, Mood> = {
  idle: REST,
  thinking: REST,
  tool: REST,
  interrupted: REST,
  confirm: REST,
  listening: { dive: 0.12, pulse: 1, presence: 1, voice: 'user' },
  assistant_speaking: { dive: 0.12, pulse: 1, presence: 1, voice: 'assistant' },
  overlap: { dive: 0.12, pulse: 1, presence: 1, voice: 'both' },
  muted: { ...REST, presence: 0.45 },
  offline: { ...REST, presence: 0.2 },
}

interface PresenceOrbProps {
  state: ConversationState
  /** Live levels from mic capture and playback; missing in the design preview. */
  levels?: RefObject<LevelMeters>
  /** Latest voice levels (0..1), exposed for tests as data attributes. */
  latest?: { user: number; assistant: number }
  /** Smaller, once the transcript needs the room. */
  compact?: boolean
}

/** TalkBack's presence: a 3D orb in the middle of the stage that reacts to the voices. */
export function PresenceOrb({ state, levels, latest, compact = false }: PresenceOrbProps) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const orb = useRef<StormOrb | null>(null)
  const mood = useRef(MOODS[state])
  const { orbMotion } = useEffectsSetting()

  useEffect(() => {
    const element = canvas.current
    if (!element || sceneDisabled()) return
    let cancelled = false
    const still = !orbMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches
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
  }, [levels, orbMotion])

  useEffect(() => {
    mood.current = MOODS[state]
    orb.current?.setMood(MOODS[state])
  }, [state])

  return (
    <div
      aria-hidden
      data-voice-user={latest?.user.toFixed(3)}
      data-voice-assistant={latest?.assistant.toFixed(3)}
      className={`relative shrink-0 rounded-pill bg-orb-bg [mask-image:radial-gradient(circle,#000_56%,transparent_71%)] ${
        compact ? 'size-orb-compact lg:size-orb-compact-lg' : 'size-orb lg:size-orb-lg'
      }`}
    >
      <canvas ref={canvas} className="block size-full rounded-pill" />
    </div>
  )
}
