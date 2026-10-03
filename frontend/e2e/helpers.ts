import { expect, type Page } from '@playwright/test'

/** The status pill in the header (design.md 6 labels). */
export const status = (page: Page) => page.locator('header').getByRole('status')

/** The visible mic button (desktop dock or mobile tab bar). */
export const micButton = (page: Page, name: string | RegExp) => page.getByRole('button', { name })

/** No horizontal page scroll (design.md 4: 375 px check). */
export async function expectNoHorizontalScroll(page: Page) {
  const { scroll, inner } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    inner: window.innerWidth,
  }))
  expect(scroll).toBeLessThanOrEqual(inner)
}

/** Newest voice level (0..1) for YOU (0) or TALKBACK (1). */
export async function laneInk(page: Page, lane: 0 | 1): Promise<number> {
  // The presence orb carries the newest level of each voice (0 = YOU, 1 = TALKBACK).
  const value = await page
    .locator('[data-voice-user]')
    .getAttribute(lane === 0 ? 'data-voice-user' : 'data-voice-assistant')
  return Number(value ?? 0)
}
