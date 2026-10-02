/** First-run flag, kept in this browser only. */
const STORAGE_KEY = 'talkback.onboarded'

export function hasOnboarded(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function markOnboarded() {
  try {
    localStorage.setItem(STORAGE_KEY, '1')
  } catch {
    // Private mode: the welcome simply shows again next time.
  }
}
