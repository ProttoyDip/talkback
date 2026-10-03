import { expect, test } from '@playwright/test'
import { micButton } from './helpers'

test('Save transcript downloads the conversation as Markdown', async ({ page }) => {
  await page.goto('/?state=assistant_speaking')
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Save transcript' }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/^talkback-.*\.md$/)
  const path = await download.path()
  const { readFileSync } = await import('node:fs')
  const text = readFileSync(path, 'utf8')
  expect(text).toContain('**You:**')
  expect(text).toContain('~~')
})

test('no Save transcript before anything was said', async ({ page }) => {
  await page.goto('/?state=idle')
  await expect(page.getByRole('button', { name: 'Save transcript' })).toBeHidden()
})

test.describe('push to talk', () => {
  test.skip(({ isMobile }) => isMobile, 'live backend checks run once, on desktop')

  test('audio leaves the page only while Space is held', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('talkback.onboarded', '1')
      localStorage.setItem('talkback.effects', JSON.stringify({ pushToTalk: true }))
    })
    const frames: number[] = []
    page.on('websocket', (socket) => socket.on('framesent', ({ payload }) => typeof payload !== 'string' && frames.push(1)))
    await page.goto('/')
    await micButton(page, 'Start talking').click()
    await expect(page.getByText('Hold Space to talk').filter({ visible: true })).toBeVisible({ timeout: 10_000 })

    await page.waitForTimeout(600)
    const idle = frames.length
    await page.waitForTimeout(600)
    expect(frames.length - idle).toBe(0) // muted while not held

    await page.locator('body').click({ position: { x: 5, y: 5 } })
    await page.keyboard.down('Space')
    await expect(page.getByText('Talking', { exact: true }).filter({ visible: true })).toBeVisible()
    await expect.poll(() => frames.length, { timeout: 5_000 }).toBeGreaterThan(idle + 10)
    await page.keyboard.up('Space')
    await expect(page.getByText('Hold Space to talk').filter({ visible: true })).toBeVisible()
  })
})
