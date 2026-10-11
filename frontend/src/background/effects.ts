/*
 * Settings kept in this browser only: the visual effects (the animated
 * background and the orb are heavy WebGL scenes; turning them off helps
 * slower laptops), push-to-talk and the opt-in recording of your own voice.
 */
import { useSyncExternalStore } from 'react'

export interface Effects {
  /** The moving particle field behind the app. */
  background: boolean
  /** The orb moves and reacts. Off: it is drawn once and stays still. */
  orbMotion: boolean
  /** Hold Space (or the mic button) to talk; muted otherwise. */
  pushToTalk: boolean
  /** Keep your own mic audio in this browser for download (SECURITY.md T10). */
  saveRecordings: boolean
}

const KEY = 'talkback.effects'
const DEFAULTS: Effects = { background: true, orbMotion: true, pushToTalk: false, saveRecordings: false }
const listeners = new Set<() => void>()

function read(): Effects {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Effects>
    return {
      background: typeof raw.background === 'boolean' ? raw.background : DEFAULTS.background,
      orbMotion: typeof raw.orbMotion === 'boolean' ? raw.orbMotion : DEFAULTS.orbMotion,
      pushToTalk: typeof raw.pushToTalk === 'boolean' ? raw.pushToTalk : DEFAULTS.pushToTalk,
      saveRecordings: typeof raw.saveRecordings === 'boolean' ? raw.saveRecordings : DEFAULTS.saveRecordings,
    }
  } catch {
    return DEFAULTS
  }
}

let current = read()

export function setEffects(next: Partial<Effects>) {
  current = { ...current, ...next }
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    // Private mode: the choice lasts until the page closes.
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useEffectsSetting(): Effects {
  return useSyncExternalStore(subscribe, () => current)
}
