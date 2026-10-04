/*
 * Settings kept in this browser only: the visual effects (the animated
 * background and the orb are heavy WebGL scenes; turning them off helps
 * slower laptops) and push-to-talk.
 */
import { useSyncExternalStore } from 'react'

export interface Effects {
  /** The moving particle field behind the app. */
  background: boolean
  /** The orb moves and reacts. Off: it is drawn once and stays still. */
  orbMotion: boolean
  /** Hold Space (or the mic button) to talk; muted otherwise. */
  pushToTalk: boolean
}

const KEY = 'talkback.effects'
const DEFAULTS: Effects = { background: true, orbMotion: true, pushToTalk: false }
const listeners = new Set<() => void>()

function read(): Effects {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Effects>
    return {
      background: typeof raw.background === 'boolean' ? raw.background : DEFAULTS.background,
      orbMotion: typeof raw.orbMotion === 'boolean' ? raw.orbMotion : DEFAULTS.orbMotion,
      pushToTalk: typeof raw.pushToTalk === 'boolean' ? raw.pushToTalk : DEFAULTS.pushToTalk,
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
