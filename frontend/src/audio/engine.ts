/*
 * Browser audio engine: mic capture (F2) and assistant playback (F3).
 * Must be started from a user gesture (browser autoplay rules).
 */
import { getMicDevice } from './device'
import captureUrl from './capture.worklet.ts?worker&url'
import playbackUrl from './playback.worklet.ts?worker&url'
import type { CaptureMessage } from './capture.worklet'
import type { PlaybackCommand, PlaybackMessage } from './playback.worklet'

export interface AudioCallbacks {
  /** A 20 ms PCM16 16 kHz frame (640 bytes). Not called while muted. */
  onFrame: (frame: ArrayBuffer) => void
  onInputLevel: (level: number) => void
  onOutputLevel: (level: number) => void
  /** samples_played counts all assistant samples since the session started. */
  onPosition: (seq: number, samplesPlayed: number) => void
}

export type MicProblem = 'blocked' | 'not_found' | 'unavailable'

/** Copy from design.md 5.6: plain, specific, with a next step. */
export const MIC_PROBLEM_COPY: Record<MicProblem, string> = {
  blocked: 'Microphone is blocked. Click the camera icon in the address bar and allow access.',
  not_found: 'No microphone found. Connect one and try again.',
  unavailable: 'The microphone is in use by another app or not available. Close it there and try again.',
}

export class MicError extends Error {
  readonly problem: MicProblem
  constructor(problem: MicProblem) {
    super(MIC_PROBLEM_COPY[problem])
    this.problem = problem
  }
}

/*
 * ADR-4: playback goes through an <audio> element (via a MediaStream) so the
 * browser's echo canceller sees what TalkBack says. Validate in week 1; if it
 * adds too much delay, set this to false to play straight to the speakers.
 */
const ROUTE_THROUGH_MEDIA_ELEMENT = true

export class AudioEngine {
  private context?: AudioContext
  private playback?: AudioWorkletNode
  private capture?: AudioWorkletNode
  private micStream?: MediaStream
  private element?: HTMLAudioElement
  private muted = false
  private readonly callbacks: AudioCallbacks

  constructor(callbacks: AudioCallbacks) {
    this.callbacks = callbacks
  }

  /** Create the audio graph and start playback. Call from a click or key press. */
  async start(): Promise<void> {
    const context = new AudioContext({ latencyHint: 'interactive' })
    this.context = context
    await Promise.all([context.audioWorklet.addModule(captureUrl), context.audioWorklet.addModule(playbackUrl)])

    const playback = new AudioWorkletNode(context, 'talkback-playback', {
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    })
    playback.port.onmessage = (event: MessageEvent<PlaybackMessage>) => {
      const message = event.data
      if (message.type === 'level') this.callbacks.onOutputLevel(message.level)
      else if (message.seq >= 0) this.callbacks.onPosition(message.seq, message.samplesPlayed)
    }
    this.playback = playback

    if (ROUTE_THROUGH_MEDIA_ELEMENT) {
      const destination = context.createMediaStreamDestination()
      playback.connect(destination)
      const element = new Audio()
      element.srcObject = destination.stream
      this.element = element
      await element.play()
    } else {
      playback.connect(context.destination)
    }
    if (context.state === 'suspended') await context.resume()
  }

  /** Ask for the microphone and start sending frames. */
  async startMic(): Promise<void> {
    const context = this.context
    if (!context) throw new Error('start() first')
    let stream: MediaStream
    try {
      const deviceId = getMicDevice()
      const audio: MediaTrackConstraints = {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: deviceId ? { ...audio, deviceId: { exact: deviceId } } : audio,
        })
      } catch (error) {
        // The saved microphone was unplugged: fall back to the default one.
        if (!deviceId || !(error instanceof DOMException) || error.name !== 'OverconstrainedError') throw error
        stream = await navigator.mediaDevices.getUserMedia({ audio })
      }
    } catch (error) {
      const name = error instanceof DOMException ? error.name : ''
      if (name === 'NotAllowedError' || name === 'SecurityError') throw new MicError('blocked')
      if (name === 'NotFoundError' || name === 'OverconstrainedError') throw new MicError('not_found')
      throw new MicError('unavailable')
    }
    this.micStream = stream

    // numberOfOutputs 0: a sink node, so the browser always runs it.
    const capture = new AudioWorkletNode(context, 'talkback-capture', { numberOfInputs: 1, numberOfOutputs: 0 })
    capture.port.onmessage = (event: MessageEvent<CaptureMessage>) => {
      if (this.muted) return // muted audio never leaves the page
      this.callbacks.onInputLevel(event.data.level)
      this.callbacks.onFrame(event.data.frame)
    }
    context.createMediaStreamSource(stream).connect(capture)
    this.capture = capture
  }

  setMuted(muted: boolean) {
    this.muted = muted
    if (muted) this.callbacks.onInputLevel(0)
  }

  /** Queue assistant audio (PCM16, 22.05 kHz). */
  enqueue(seq: number, pcm: Int16Array) {
    const command: PlaybackCommand = { type: 'chunk', seq, pcm }
    this.playback?.port.postMessage(command, [pcm.buffer])
  }

  /** Stop playback now (interruption). The worklet reports the final position. */
  flush() {
    const command: PlaybackCommand = { type: 'flush' }
    this.playback?.port.postMessage(command)
  }

  async close() {
    this.micStream?.getTracks().forEach((track) => track.stop())
    this.capture?.disconnect()
    this.playback?.disconnect()
    if (this.element) this.element.srcObject = null
    await this.context?.close()
  }
}
