/*
 * Visual effects switches (Settings > Visual effects), kept in this browser.
 * The animated background and the orb are heavy WebGL scenes; turning them
 * off helps slower laptops and saves battery.
 */
import { useSyncExternalStore } from 'react'

export interface Effects {
  /** The moving particle field behind the app. */
  background: boolean
  /** The orb moves and reacts. Off: it is drawn once and stays still. */
  orbMotion: boolean
}

const KEY = 'talkback.effects'
const DEFAULTS: Effects = { background: true, orbMotion: true }
const listeners = new Set<() => void>()

function read(): Effects {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Effects>
    return {
      background: typeof raw.background === 'boolean' ? raw.background : DEFAULTS.background,
      orbMotion: typeof raw.orbMotion === 'boolean' ? raw.orbMotion : DEFAULTS.orbMotion,
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
