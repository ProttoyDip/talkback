/*
 * Motion tokens for the `motion` library, read from tokens.css so the values
 * live in one place. motion/react wants seconds and cubic-bezier arrays.
 */
type Bezier = [number, number, number, number]

const root = getComputedStyle(document.documentElement)

function seconds(name: string): number {
  return parseFloat(root.getPropertyValue(name)) / 1000
}

function bezier(name: string): Bezier {
  const match = root.getPropertyValue(name).match(/cubic-bezier\(([^)]+)\)/)
  const parts = match ? match[1].split(',').map(Number) : [0, 0, 1, 1]
  return parts as Bezier
}

export const dur = {
  instant: seconds('--dur-instant'),
  fast: seconds('--dur-fast'),
  base: seconds('--dur-base'),
  slow: seconds('--dur-slow'),
}

export const ease = {
  out: bezier('--ease-out'),
  in: bezier('--ease-in'),
}

/** Entering: opacity plus a small rise. */
export const enter = { duration: dur.base, ease: ease.out }
/** Leaving. */
export const exit = { duration: dur.fast, ease: ease.in }
