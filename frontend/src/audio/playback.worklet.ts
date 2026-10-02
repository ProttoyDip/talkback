/*
 * Assistant playback (architecture.md 2.1): a queue of 22.05 kHz PCM16 chunks,
 * resampled to the device rate. It counts exactly how many source samples
 * have been played, reports the position every 100 ms and right after a
 * flush, and stops at once on flush (FR-5).
 */
import { int16ToFloat, levelFromRms, Resampler } from './dsp'

const SOURCE_RATE = 22_050

export type PlaybackCommand =
  | { type: 'chunk'; seq: number; pcm: Int16Array }
  | { type: 'flush' }

export type PlaybackMessage =
  | { type: 'position'; seq: number; samplesPlayed: number; playing: boolean }
  | { type: 'level'; level: number }

interface Chunk {
  seq: number
  data: Float32Array // at the device rate
  sourceSamples: number
  read: number
}

class PlaybackProcessor extends AudioWorkletProcessor {
  private resampler = new Resampler(SOURCE_RATE, sampleRate)
  private queue: Chunk[] = []
  /** Source samples of fully played chunks since the session started. */
  private completedSource = 0
  private lastSeq = -1
  private framesSinceReport = 0
  private readonly reportEvery = Math.round(sampleRate * 0.1)
  private wasPlaying = false
  // The level meter is posted 20 times a second, not every 128-frame block.
  private levelFrames = 0
  private levelSquares = 0
  private readonly levelEvery = Math.round(sampleRate * 0.05)

  constructor() {
    super()
    this.port.onmessage = (event: MessageEvent<PlaybackCommand>) => {
      const command = event.data
      if (command.type === 'chunk') {
        this.queue.push({
          seq: command.seq,
          data: this.resampler.process(int16ToFloat(command.pcm)),
          sourceSamples: command.pcm.length,
          read: 0,
        })
      } else {
        // Count what was already heard of the current chunk, then drop the rest.
        this.completedSource = this.samplesPlayed()
        this.queue = []
        this.resampler.reset()
        this.report(false)
      }
    }
  }

  private samplesPlayed(): number {
    const current = this.queue[0]
    if (!current || current.data.length === 0) return this.completedSource
    return this.completedSource + Math.round((current.read / current.data.length) * current.sourceSamples)
  }

  private report(playing: boolean) {
    const message: PlaybackMessage = {
      type: 'position',
      seq: this.queue[0]?.seq ?? this.lastSeq,
      samplesPlayed: this.samplesPlayed(),
      playing,
    }
    this.port.postMessage(message)
    this.framesSinceReport = 0
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const out = outputs[0]?.[0]
    if (!out) return true
    let sumSquares = 0
    for (let i = 0; i < out.length; i++) {
      const chunk = this.queue[0]
      if (!chunk) {
        out[i] = 0
        continue
      }
      const sample = chunk.data[chunk.read++]
      out[i] = sample
      sumSquares += sample * sample
      this.lastSeq = chunk.seq
      if (chunk.read >= chunk.data.length) {
        this.completedSource += chunk.sourceSamples
        this.queue.shift()
      }
    }
    // Copy to any extra output channels.
    for (let c = 1; c < outputs[0].length; c++) outputs[0][c].set(out)

    const playing = this.queue.length > 0 || sumSquares > 0
    this.framesSinceReport += out.length
    if (playing && this.framesSinceReport >= this.reportEvery) this.report(true)
    if (this.wasPlaying && !playing) this.report(false) // finished: final position
    this.wasPlaying = playing
    this.levelFrames += out.length
    this.levelSquares += sumSquares
    if (this.levelFrames >= this.levelEvery) {
      const level: PlaybackMessage = { type: 'level', level: levelFromRms(Math.sqrt(this.levelSquares / this.levelFrames)) }
      this.port.postMessage(level)
      this.levelFrames = 0
      this.levelSquares = 0
    }
    return true
  }
}

registerProcessor('talkback-playback', PlaybackProcessor)
