/*
 * Small DSP helpers shared by the audio worklets. Pure functions and classes,
 * so they run in the AudioWorklet scope and in unit tests.
 */

/** Windowed-sinc low-pass filter taps (Blackman window), normalised to unity gain. */
export function lowpassTaps(cutoffHz: number, sampleRate: number, length = 63): Float32Array {
  const taps = new Float32Array(length)
  const fc = cutoffHz / sampleRate
  const middle = (length - 1) / 2
  let sum = 0
  for (let i = 0; i < length; i++) {
    const x = i - middle
    const sinc = x === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * x) / (Math.PI * x)
    const window =
      0.42 - 0.5 * Math.cos((2 * Math.PI * i) / (length - 1)) + 0.08 * Math.cos((4 * Math.PI * i) / (length - 1))
    taps[i] = sinc * window
    sum += taps[i]
  }
  for (let i = 0; i < length; i++) taps[i] /= sum
  return taps
}

/**
 * Streaming sample-rate converter. When downsampling it first applies a
 * low-pass filter below the new Nyquist frequency, so content above it (for
 * example ultrasonic carriers) is removed, not folded back (SECURITY.md T2).
 * Then it interpolates linearly. State carries across blocks.
 */
export class Resampler {
  private readonly step: number
  private readonly taps?: Float32Array
  private history: Float32Array
  private carry: Float32Array = new Float32Array(0)
  private position = 0

  constructor(fromRate: number, toRate: number) {
    this.step = fromRate / toRate
    if (toRate < fromRate) this.taps = lowpassTaps(0.45 * toRate, fromRate)
    this.history = new Float32Array(this.taps ? this.taps.length - 1 : 0)
  }

  private filter(input: Float32Array): Float32Array {
    const taps = this.taps
    if (!taps) return input
    const span = taps.length - 1
    const extended = new Float32Array(span + input.length)
    extended.set(this.history)
    extended.set(input, span)
    const out = new Float32Array(input.length)
    for (let n = 0; n < input.length; n++) {
      let acc = 0
      for (let k = 0; k < taps.length; k++) acc += taps[k] * extended[n + span - k]
      out[n] = acc
    }
    this.history = extended.slice(extended.length - span)
    return out
  }

  process(input: Float32Array): Float32Array {
    const filtered = this.filter(input)
    const work = new Float32Array(this.carry.length + filtered.length)
    work.set(this.carry)
    work.set(filtered, this.carry.length)

    const out: number[] = []
    let t = this.position
    while (t + 1 < work.length) {
      const i = Math.floor(t)
      const frac = t - i
      out.push(work[i] * (1 - frac) + work[i + 1] * frac)
      t += this.step
    }
    // The next read may fall beyond this block; keep the offset so no input
    // samples are skipped or repeated across block boundaries.
    const keep = Math.min(Math.floor(t), work.length)
    this.carry = work.slice(keep)
    this.position = t - keep
    return Float32Array.from(out)
  }

  reset() {
    this.history.fill(0)
    this.carry = new Float32Array(0)
    this.position = 0
  }
}

export function floatToInt16(value: number): number {
  const clamped = Math.max(-1, Math.min(1, value))
  return clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff)
}

export function int16ToFloat(pcm: Int16Array): Float32Array {
  const out = new Float32Array(pcm.length)
  for (let i = 0; i < pcm.length; i++) out[i] = pcm[i] / 0x8000
  return out
}

/** Map RMS to a 0..1 meter level on a 60 dB scale (-60 dBFS = 0, 0 dBFS = 1). */
export function levelFromRms(rms: number): number {
  if (rms <= 0) return 0
  const db = 20 * Math.log10(rms)
  return Math.max(0, Math.min(1, (db + 60) / 60))
}
