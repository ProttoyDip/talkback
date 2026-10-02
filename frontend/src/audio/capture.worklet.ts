/*
 * Mic capture (architecture.md 2.1): resample the microphone to 16 kHz mono
 * with an anti-aliasing filter, and post 20 ms PCM16 frames (640 bytes) plus
 * the frame's level. Runs on the audio thread.
 */
import { floatToInt16, levelFromRms, Resampler } from './dsp'

const TARGET_RATE = 16_000
const FRAME_SAMPLES = 320 // 20 ms

export interface CaptureMessage {
  frame: ArrayBuffer
  level: number
}

class CaptureProcessor extends AudioWorkletProcessor {
  private resampler = new Resampler(sampleRate, TARGET_RATE)
  private frame = new Int16Array(FRAME_SAMPLES)
  private filled = 0
  private sumSquares = 0

  process(inputs: Float32Array[][]): boolean {
    const channel = inputs[0]?.[0]
    if (!channel) return true
    for (const sample of this.resampler.process(channel)) {
      this.frame[this.filled++] = floatToInt16(sample)
      this.sumSquares += sample * sample
      if (this.filled === FRAME_SAMPLES) {
        const message: CaptureMessage = {
          frame: this.frame.buffer,
          level: levelFromRms(Math.sqrt(this.sumSquares / FRAME_SAMPLES)),
        }
        this.port.postMessage(message, [this.frame.buffer])
        this.frame = new Int16Array(FRAME_SAMPLES)
        this.filled = 0
        this.sumSquares = 0
      }
    }
    return true
  }
}

registerProcessor('talkback-capture', CaptureProcessor)
