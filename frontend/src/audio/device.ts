/** The chosen microphone, kept in this browser only. Empty means the default. */
const KEY = 'talkback.micDevice'

export function getMicDevice(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

export function setMicDevice(id: string) {
  try {
    if (id) localStorage.setItem(KEY, id)
    else localStorage.removeItem(KEY)
  } catch {
    // Private mode: the choice lasts until the page closes.
  }
}
