/** A 16-bit mono PCM WAV file from raw frames (the opt-in recording, SECURITY.md T10). */
export function wavFromPcm16(frames: Int16Array[], sampleRate: number): Blob {
  const samples = frames.reduce((n, f) => n + f.length, 0)
  const header = new DataView(new ArrayBuffer(44))
  const text = (offset: number, value: string) =>
    [...value].forEach((c, i) => header.setUint8(offset + i, c.charCodeAt(0)))
  text(0, 'RIFF')
  header.setUint32(4, 36 + samples * 2, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  header.setUint32(16, 16, true) // fmt chunk size
  header.setUint16(20, 1, true) // PCM
  header.setUint16(22, 1, true) // mono
  header.setUint32(24, sampleRate, true)
  header.setUint32(28, sampleRate * 2, true) // bytes per second
  header.setUint16(32, 2, true) // bytes per frame
  header.setUint16(34, 16, true) // bits per sample
  text(36, 'data')
  header.setUint32(40, samples * 2, true)
  return new Blob([header.buffer, ...frames.map((f) => f.buffer as ArrayBuffer)], { type: 'audio/wav' })
}
