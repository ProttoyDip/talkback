/*
 * Replay transport: plays docs/fixtures/demo_session.jsonl with its real
 * timing, so the screen can be developed and demoed without a backend.
 * It answers mute and confirmation locally. The fixture has no audio, so it
 * creates a quiet voice-like tone for each audio.chunk.
 */
import fixture from '../../../docs/fixtures/demo_session.jsonl?raw'
import { SERVER_SAMPLE_RATE, type ClientMessage, type ServerEvent } from './protocol'
import type { Transport, TransportHandlers } from './transport'

interface Line {
  t_ms: number
  event: ServerEvent
}

const LINES: Line[] = fixture
  .trim()
  .split('\n')
  .map((line) => JSON.parse(line) as Line)

/** A soft, slightly moving tone, so playback and level meters have real audio. */
function tone(seq: number, samples: number): Int16Array {
  const pcm = new Int16Array(samples)
  const pitch = 150 + 30 * Math.sin(seq * 0.7)
  for (let i = 0; i < samples; i++) {
    const t = i / SERVER_SAMPLE_RATE
    // Syllable-like amplitude: 4-5 bumps per second.
    const syllable = 0.35 + 0.65 * Math.abs(Math.sin(Math.PI * (t * 4.5 + seq * 0.37)))
    const edge = Math.min(1, i / 200, (samples - i) / 200)
    const wave = Math.sin(2 * Math.PI * pitch * t) + 0.35 * Math.sin(4 * Math.PI * pitch * t)
    pcm[i] = Math.round(wave * syllable * edge * 5000)
  }
  return pcm
}

export class ReplayTransport implements Transport {
  private handlers?: TransportHandlers
  private timers: ReturnType<typeof setTimeout>[] = []
  private readonly speed: number

  /** speed > 1 plays the script faster (end-to-end tests use ?speed=). */
  constructor(speed = 1) {
    this.speed = speed > 0 ? speed : 1
  }

  connect(handlers: TransportHandlers) {
    this.handlers = handlers
    this.start()
  }

  private start() {
    this.handlers?.onConnection('open')
    for (const { t_ms, event } of LINES) {
      this.timers.push(
        setTimeout(() => {
          this.handlers?.onEvent(event)
          if (event.type === 'audio.chunk') this.handlers?.onAudio(event.seq, tone(event.seq, event.samples))
        }, t_ms / this.speed),
      )
    }
  }

  send(message: ClientMessage) {
    const emit = (event: ServerEvent) => this.handlers?.onEvent(event)
    if (message.type === 'control.mute') {
      emit({ type: 'state', state: message.muted ? 'muted' : 'idle' })
    } else if (message.type === 'tool.confirm') {
      emit({ type: 'state', state: 'idle' })
    }
  }

  sendAudio() {
    // The replay does not listen.
  }

  reconnect() {
    this.stop()
    this.handlers?.onConnection('connecting')
    this.start()
  }

  close() {
    this.stop()
  }

  private stop() {
    this.timers.forEach(clearTimeout)
    this.timers = []
  }
}
