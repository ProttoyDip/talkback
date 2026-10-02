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

/** Share of pixels drawn in a timeline lane canvas (0 = TALKBACK lane is index 1). */
export async function laneInk(page: Page, lane: 0 | 1): Promise<number> {
  return page.locator('section[aria-hidden] canvas').nth(lane).evaluate((canvas: HTMLCanvasElement) => {
    const ctx = canvas.getContext('2d')
    if (!ctx || canvas.width === 0) return 0
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
    let drawn = 0
    for (let i = 3; i < data.length; i += 4) if (data[i] > 0) drawn++
    return drawn / (canvas.width * canvas.height)
  })
}
