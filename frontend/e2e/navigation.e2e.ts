import { expect, test } from '@playwright/test'

test('M opens Memory, K opens Skills, Esc closes (design.md 7)', async ({ page }) => {
  await page.goto('/?state=assistant_speaking')
  await page.keyboard.press('m')
  const memory = page.getByRole('complementary', { name: 'Memory' })
  await expect(memory).toContainText('Nothing remembered yet.')
  await expect(page.getByRole('button', { name: 'Close Memory' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(memory).toBeHidden()

  await page.keyboard.press('k')
  await expect(page.getByRole('complementary', { name: 'Skills' })).toBeVisible()
  await page.getByRole('button', { name: 'Close Skills' }).click()
  await expect(page.getByRole('complementary', { name: 'Skills' })).toBeHidden()
})

test('Settings is marked as not available yet', async ({ page }) => {
  await page.goto('/?state=idle')
  await expect(page.getByRole('button', { name: 'Settings (not available yet)' })).toHaveAttribute(
    'aria-disabled',
    'true',
  )
})

test('keyboard focus shows a 2 px ring', async ({ page, isMobile }) => {
  test.skip(isMobile, 'keyboard check on desktop')
  await page.goto('/?state=idle')
  await page.keyboard.press('Tab')
  const focused = page.locator(':focus')
  await expect(focused).toHaveCSS('outline-style', 'solid')
  await expect(focused).toHaveCSS('outline-width', '2px')
})

test('touch targets are at least 44 px and the mic is 72 px', async ({ page }) => {
  await page.goto('/?state=assistant_speaking')
  const mic = page.getByRole('button', { name: 'Mute microphone' })
  const box = await mic.boundingBox()
  expect(box?.width).toBe(72)
  expect(box?.height).toBe(72)
  for (const button of await page.locator('nav button:visible').all()) {
    const b = await button.boundingBox()
    expect(Math.min(b?.width ?? 0, b?.height ?? 0)).toBeGreaterThanOrEqual(44)
  }
})

test('layout: rail on desktop, tab bar on mobile (design.md 4)', async ({ page, isMobile }) => {
  await page.goto('/?state=idle')
  const navs = page.getByRole('navigation', { name: 'Main' })
  await expect(navs.filter({ visible: true })).toHaveCount(1)
  const visible = navs.filter({ visible: true })
  const box = await visible.boundingBox()
  if (isMobile) expect(box?.y ?? 0).toBeGreaterThan(600) // bottom tab bar
  else expect(box?.width).toBe(64) // left rail
})

test('reduced motion: nothing keeps animating', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/?state=tool') // has a running tool spinner
  await page.waitForTimeout(800)
  const running = await page.evaluate(
    () => document.getAnimations().filter((a) => a.playState === 'running').length,
  )
  expect(running).toBe(0)
})
