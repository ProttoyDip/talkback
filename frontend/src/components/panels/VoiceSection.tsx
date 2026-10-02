import { useEffect, useRef, useState } from 'react'
import { getMicDevice, setMicDevice } from '../../audio/device'
import { SectionTitle } from './shared'

interface Input {
  id: string
  label: string
}

/** Root-mean-square level of a time-domain buffer, scaled so speech reaches ~1. */
function level(buffer: Float32Array<ArrayBuffer>): number {
  let sum = 0
  for (const sample of buffer) sum += sample * sample
  return Math.min(1, Math.sqrt(sum / buffer.length) * 4)
}

/**
 * Settings > Voice (design.md 5.5): pick the input device and watch a live
 * level meter. The choice applies the next time a conversation starts.
 */
export function VoiceSection() {
  const [inputs, setInputs] = useState<Input[]>([])
  const [selected, setSelected] = useState(getMicDevice)
  const [problem, setProblem] = useState<string>()
  const bar = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    let stream: MediaStream | undefined
    let context: AudioContext | undefined
    let frame = 0
    let cancelled = false

    async function run() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: selected ? { deviceId: { exact: selected } } : true,
        })
      } catch (error) {
        if (cancelled) return
        const name = error instanceof DOMException ? error.name : ''
        setProblem(
          name === 'NotAllowedError'
            ? 'Microphone is blocked. Allow it in the address bar to see the level.'
            : 'No microphone could be opened.',
        )
        return
      }
      if (cancelled) return stream.getTracks().forEach((track) => track.stop())
      setProblem(undefined)

      // Labels are only available once permission is granted.
      const devices = await navigator.mediaDevices.enumerateDevices()
      if (cancelled) return
      setInputs(
        devices
          .filter((d) => d.kind === 'audioinput' && d.deviceId)
          .map((d, i) => ({ id: d.deviceId, label: d.label || `Microphone ${i + 1}` })),
      )

      context = new AudioContext()
      const analyser = context.createAnalyser()
      analyser.fftSize = 1024
      context.createMediaStreamSource(stream).connect(analyser)
      const buffer = new Float32Array(analyser.fftSize)
      const tick = () => {
        analyser.getFloatTimeDomainData(buffer)
        if (bar.current) bar.current.style.transform = `scaleX(${level(buffer)})`
        frame = requestAnimationFrame(tick)
      }
      tick()
    }
    void run()

    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
      stream?.getTracks().forEach((track) => track.stop())
      void context?.close()
    }
  }, [selected])

  return (
    <section aria-label="Voice">
      <SectionTitle>Voice</SectionTitle>
      <label htmlFor="mic-device" className="mb-1 block text-body font-medium text-text">
        Microphone
      </label>
      <select
        id="mic-device"
        value={selected}
        onChange={(e) => {
          setSelected(e.target.value)
          setMicDevice(e.target.value)
        }}
        className="min-h-target w-full rounded-input border border-border bg-bg px-3 text-body text-text"
      >
        <option value="">Default microphone</option>
        {inputs.map((input) => (
          <option key={input.id} value={input.id}>
            {input.label}
          </option>
        ))}
      </select>
      <p className="mt-1 text-data text-text-muted">Applies the next time you start a conversation.</p>

      <p className="mb-1 mt-4 text-body font-medium text-text">
        Input level
      </p>
      {problem ? (
        <p role="alert" className="text-data text-danger">
          {problem}
        </p>
      ) : (
        <div
          aria-hidden
          className="h-2 overflow-hidden rounded-pill border border-border bg-bg"
        >
          <span ref={bar} className="block h-full origin-left scale-x-0 bg-voice-user" />
        </div>
      )}
    </section>
  )
}
