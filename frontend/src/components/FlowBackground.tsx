import { useEffect, useRef } from 'react'
import type { FlowScene } from '../background/flowScene'
import type { ConversationState } from '../state/types'
import { useEffectsSetting } from '../background/effects'
import { sceneDisabled } from './sceneSupport'

/**
 * How far the camera dives into the field for each conversation state
 * (0 = high and calm, 1 = skimming the surface). The swell grows with it.
 */
const DEPTH: Record<ConversationState, number> = {
  idle: 0,
  muted: 0,
  offline: 0,
  listening: 0.2,
  thinking: 0.25,
  tool: 0.25,
  confirm: 0.1,
  interrupted: 0.25,
  assistant_speaking: 0.35,
  overlap: 0.45,
}


/** The animated "Flow Wave" background (src/background/flowScene.ts). */
export function FlowBackground({ state }: { state: ConversationState }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const scene = useRef<FlowScene | null>(null)
  const depth = useRef(DEPTH[state])
  const { background } = useEffectsSetting()

  useEffect(() => {
    const element = canvas.current
    if (!element || !background || sceneDisabled()) return
    let cancelled = false
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // Loaded on demand: the 3D library is not needed for the first paint.
    void import('../background/flowScene').then(({ createFlowScene }) => {
      if (cancelled) return
      scene.current = createFlowScene(element, still)
      scene.current?.setScroll(depth.current)
    })
    return () => {
      cancelled = true
      scene.current?.dispose()
      scene.current = null
    }
  }, [background])

  useEffect(() => {
    depth.current = DEPTH[state]
    scene.current?.setScroll(DEPTH[state])
  }, [state])

  return (
    <canvas
      ref={canvas}
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 h-dvh w-screen"
    />
  )
}
