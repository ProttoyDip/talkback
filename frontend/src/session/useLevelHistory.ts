import { useEffect, useState, type RefObject } from 'react'
import type { TimelineData } from '../state/types'

export const WINDOW_SECONDS = 10
const STEP_MS = 100
const STEPS = (WINDOW_SECONDS * 1000) / STEP_MS

/** Current input and output levels (0..1). Mic capture and playback write them. */
export interface LevelMeters {
  user: number
  assistant: number
}

/**
 * Samples the level meters every 100 ms into a rolling 10-second window for
 * the duplex timeline. Interrupt times (performance.now() ms) are converted to
 * positions in the window.
 */
export function useLevelHistory(meters: RefObject<LevelMeters>, interrupts: number[]): TimelineData {
  const [snapshot, setSnapshot] = useState(() => ({
    now: performance.now(),
    user: new Array<number>(STEPS).fill(0),
    assistant: new Array<number>(STEPS).fill(0),
  }))

  useEffect(() => {
    const id = setInterval(() => {
      const { user, assistant } = meters.current
      setSnapshot((prev) => ({
        now: performance.now(),
        user: [...prev.user.slice(1), user],
        assistant: [...prev.assistant.slice(1), assistant],
      }))
    }, STEP_MS)
    return () => clearInterval(id)
  }, [meters])

  const windowStart = snapshot.now - WINDOW_SECONDS * 1000
  return {
    windowSeconds: WINDOW_SECONDS,
    user: snapshot.user,
    assistant: snapshot.assistant,
    interrupts: interrupts
      .filter((at) => at >= windowStart && at <= snapshot.now)
      .map((at) => (at - windowStart) / 1000),
  }
}
