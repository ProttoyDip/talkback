import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { initialModel, reduce } from './model'
import type { ClientMessage, ServerEvent } from './protocol'
import { ReplayTransport } from './replay'
import { LiveTransport, type Transport } from './transport'

export type SessionMode = 'live' | 'replay'

/** Receives assistant audio (PCM16, 22.05 kHz). The playback layer sets it. */
export type AudioSink = (seq: number, pcm: Int16Array) => void

/**
 * The session starts only when the user starts it (SECURITY.md T2), which is
 * also the user gesture browsers require before audio can play.
 */
export function useSession(mode: SessionMode) {
  const [model, dispatch] = useReducer(reduce, initialModel)
  const [started, setStarted] = useState(false)
  const [muted, setMutedState] = useState(false)
  const transportRef = useRef<Transport | null>(null)
  const audioSinkRef = useRef<AudioSink | null>(null)
  /** Side effects for events (for example: flush playback on audio.flush). */
  const onEventRef = useRef<((event: ServerEvent) => void) | null>(null)

  useEffect(() => {
    if (!started) return
    const transport: Transport = mode === 'replay' ? new ReplayTransport() : new LiveTransport()
    transportRef.current = transport
    transport.connect({
      onEvent: (event) => {
        onEventRef.current?.(event)
        dispatch({ kind: 'event', event, at: performance.now() })
      },
      onAudio: (seq, pcm) => audioSinkRef.current?.(seq, pcm),
      onConnection: (connection) => dispatch({ kind: 'connection', connection }),
    })
    return () => {
      transport.close()
      transportRef.current = null
    }
  }, [mode, started])

  const start = useCallback(() => setStarted(true), [])

  const send = useCallback((message: ClientMessage) => transportRef.current?.send(message), [])
  const sendAudio = useCallback((frame: ArrayBuffer) => transportRef.current?.sendAudio(frame), [])

  const setMuted = useCallback((next: boolean) => {
    setMutedState(next)
    transportRef.current?.send({ type: 'control.mute', muted: next })
  }, [])

  const answerConfirm = useCallback(
    (approved: boolean) => {
      if (!model.confirm) return
      transportRef.current?.send({ type: 'tool.confirm', call_id: model.confirm.callId, approved })
      dispatch({ kind: 'confirm-answered' })
    },
    [model.confirm],
  )

  const reconnect = useCallback(() => transportRef.current?.reconnect(), [])

  /** Connect the audio layer: where assistant audio goes, and event side effects. */
  const attachAudio = useCallback((sink: AudioSink, onEvent: (event: ServerEvent) => void) => {
    audioSinkRef.current = sink
    onEventRef.current = onEvent
  }, [])

  return {
    model,
    started,
    start,
    muted,
    setMuted,
    answerConfirm,
    reconnect,
    send,
    sendAudio,
    attachAudio,
  }
}
