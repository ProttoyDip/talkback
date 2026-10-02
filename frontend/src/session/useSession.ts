import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { initialModel, reduce } from './model'
import { ReplayTransport } from './replay'
import { LiveTransport, type Transport } from './transport'

export type SessionMode = 'live' | 'replay'

/** Receives assistant audio (PCM16, 22.05 kHz). The playback layer sets it. */
export type AudioSink = (seq: number, pcm: Int16Array) => void

export function useSession(mode: SessionMode) {
  const [model, dispatch] = useReducer(reduce, initialModel)
  const [muted, setMutedState] = useState(false)
  const transportRef = useRef<Transport | null>(null)
  const audioSinkRef = useRef<AudioSink | null>(null)

  useEffect(() => {
    const transport: Transport = mode === 'replay' ? new ReplayTransport() : new LiveTransport()
    transportRef.current = transport
    dispatch({ kind: 'reset' })
    transport.connect({
      onEvent: (event) => dispatch({ kind: 'event', event, at: performance.now() }),
      onAudio: (seq, pcm) => audioSinkRef.current?.(seq, pcm),
      onConnection: (connection) => dispatch({ kind: 'connection', connection }),
    })
    return () => {
      transport.close()
      transportRef.current = null
    }
  }, [mode])

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

  return { model, muted, setMuted, answerConfirm, reconnect, transportRef, audioSinkRef }
}
