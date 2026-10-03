import { expect, test } from '@playwright/test'
import { expectNoHorizontalScroll, laneInk, micButton, status } from './helpers'

// The shared demo fixture, played 4x faster (about 7 seconds).
test('replay plays the full demo conversation', async ({ page }) => {
  await page.goto('/?replay&speed=4')

  // Nothing starts until the user starts it (SECURITY.md T2).
  await expect(status(page)).toContainText('READY')
  await expect(page.getByText('Interrupt me any time.')).toBeVisible()
  const quietInk = await laneInk(page, 1)
  await micButton(page, 'Start talking').click()

  // Captions, tool chips and a backchannel.
  await expect(page.getByText('What does full-duplex mean?')).toBeVisible()
  await expect(page.getByRole('button', { name: /3 sources/ })).toBeVisible()
  await expect(page.getByText('Weather from Open-Meteo')).toBeVisible()
  await expect(page.getByText('· kept going')).toBeVisible()

  // TalkBack's level follows the audio it actually plays.
  await expect.poll(() => laneInk(page, 1), { timeout: 10_000 }).toBeGreaterThan(Math.max(0.05, quietInk * 3))

  // The interruption: unheard words stay, struck through.
  const unheard = page.locator('[aria-describedby]', { hasText: "so take a light jacket if you're out after dinner." })
  await expect(unheard).toBeVisible()
  await expect(unheard).toHaveCSS('text-decoration-line', 'line-through')
  await expect(page.getByText('No, tomorrow.')).toBeVisible()

  // The demo ends asking for permission; answering clears it.
  const card = page.getByRole('alertdialog')
  await expect(card).toContainText('Delete the memory “Home city is Lisbon”?')
  await expect(status(page)).toContainText('NEEDS YOUR OK')
  await card.getByRole('button', { name: 'No' }).click()
  await expect(card).toBeHidden()
  await expect(status(page)).toContainText('READY')

  await expectNoHorizontalScroll(page)
})

test('the replay never asks for the microphone', async ({ page }) => {
  await page.addInitScript(() => {
    ;(window as unknown as { micRequests: number }).micRequests = 0
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    navigator.mediaDevices.getUserMedia = (constraints) => {
      ;(window as unknown as { micRequests: number }).micRequests++
      return original(constraints)
    }
  })
  await page.goto('/?replay&speed=4')
  await micButton(page, 'Start talking').click()
  await expect(page.getByText('What does full-duplex mean?')).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { micRequests: number }).micRequests)).toBe(0)
})
