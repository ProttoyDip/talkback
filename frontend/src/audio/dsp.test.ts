import { describe, expect, it } from 'vitest'
import { floatToInt16, levelFromRms, lowpassTaps, Resampler } from './dsp'

function sine(freq: number, rate: number, seconds: number) {
  const n = Math.round(rate * seconds)
  return Float32Array.from({ length: n }, (_, i) => Math.sin((2 * Math.PI * freq * i) / rate))
}

function rms(values: Float32Array) {
  return Math.sqrt(values.reduce((s, v) => s + v * v, 0) / values.length)
}

/** Feed a signal in 128-sample blocks, like an AudioWorklet. */
function stream(resampler: Resampler, input: Float32Array) {
  const parts: Float32Array[] = []
  for (let i = 0; i < input.length; i += 128) parts.push(resampler.process(input.subarray(i, i + 128)))
  const out = new Float32Array(parts.reduce((n, p) => n + p.length, 0))
  let offset = 0
  for (const p of parts) {
    out.set(p, offset)
    offset += p.length
  }
  return out
}

describe('Resampler', () => {
  it('converts 48 kHz to 16 kHz with the right length across blocks', () => {
    const out = stream(new Resampler(48_000, 16_000), sine(440, 48_000, 1))
    expect(Math.abs(out.length - 16_000)).toBeLessThanOrEqual(2)
  })

  it('keeps speech-band tones', () => {
    const out = stream(new Resampler(48_000, 16_000), sine(1_000, 48_000, 0.5))
    expect(rms(out.subarray(200))).toBeGreaterThan(0.6) // a full-scale sine has RMS 0.707
  })

  it('removes content above the new Nyquist frequency instead of folding it back (T2)', () => {
    // 20 kHz would alias to 4 kHz at a 16 kHz rate without the filter.
    const out = stream(new Resampler(48_000, 16_000), sine(20_000, 48_000, 0.5))
    expect(rms(out.subarray(200))).toBeLessThan(0.01)
  })

  it('upsamples 22.05 kHz to 48 kHz', () => {
    const out = stream(new Resampler(22_050, 48_000), sine(300, 22_050, 1))
    expect(Math.abs(out.length - 48_000)).toBeLessThanOrEqual(3)
  })
})

describe('helpers', () => {
  it('low-pass taps have unity gain', () => {
    expect(lowpassTaps(7_200, 48_000).reduce((a, b) => a + b, 0)).toBeCloseTo(1, 6)
  })

  it('converts floats to PCM16 with clipping', () => {
    expect(floatToInt16(1)).toBe(32767)
    expect(floatToInt16(-1)).toBe(-32768)
    expect(floatToInt16(2)).toBe(32767)
    expect(floatToInt16(0)).toBe(0)
  })

  it('maps RMS to a 0..1 level', () => {
    expect(levelFromRms(0)).toBe(0)
    expect(levelFromRms(1)).toBe(1)
    expect(levelFromRms(0.001)).toBeCloseTo(0, 5)
  })
})
