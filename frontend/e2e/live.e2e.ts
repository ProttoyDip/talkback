import { expect, test, type Page } from '@playwright/test'
import { laneInk, micButton, status } from './helpers'

// Live sessions against the real backend. The backend allows 3 connections
// per IP, so these run one at a time and on the desktop project only.
test.describe.configure({ mode: 'serial' })
test.skip(({ isMobile }) => isMobile, 'live backend checks run once, on desktop')

// These tests are about the session, not the first-run welcome.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('talkback.onboarded', '1'))
})

function recordSocket(page: Page) {
  const frames: number[] = []
  const messages: Array<Record<string, unknown>> = []
  page.on('websocket', (socket) => {
    socket.on('framesent', ({ payload }) => {
      if (typeof payload === 'string') messages.push(JSON.parse(payload))
      else frames.push(payload.length)
    })
  })
  return { frames, messages }
}

test('starts a session and streams 20 ms microphone frames', async ({ page }) => {
  const sent = recordSocket(page)
  await page.goto('/')
  await expect(status(page)).toContainText('READY')
  await micButton(page, 'Start talking').click()

  await expect.poll(() => sent.frames.length, { timeout: 10_000 }).toBeGreaterThan(40)
  expect(sent.messages[0]).toEqual({ type: 'session.start', client_sample_rate: 16000 })
  expect(new Set(sent.frames)).toEqual(new Set([640])) // PCM16, 16 kHz, 20 ms

  // The fake microphone's test tone shows on the YOU lane.
  await expect.poll(() => laneInk(page, 0), { timeout: 5_000 }).toBeGreaterThan(0.01)
})

test('mute stops audio leaving the page and tells the server', async ({ page }) => {
  const sent = recordSocket(page)
  await page.goto('/')
  await micButton(page, 'Start talking').click()
  await expect.poll(() => sent.frames.length, { timeout: 10_000 }).toBeGreaterThan(10)

  await micButton(page, 'Mute microphone').click()
  await expect(status(page)).toContainText('MUTED')
  await expect(micButton(page, 'Unmute microphone')).toHaveAttribute('aria-pressed', 'true')
  expect(sent.messages).toContainEqual({ type: 'control.mute', muted: true })

  const whileMuted = sent.frames.length
  await page.waitForTimeout(600)
  expect(sent.frames.length).toBe(whileMuted)

  // Space toggles it back (design.md 7).
  await page.locator('body').click({ position: { x: 5, y: 5 } })
  await page.keyboard.press('Space')
  await expect(status(page)).toContainText('READY')
  await expect.poll(() => sent.frames.length, { timeout: 5_000 }).toBeGreaterThan(whileMuted + 10)
})

test('a lost connection shows the reconnecting message', async ({ page }) => {
  await page.route('**/api/session', (route) => route.abort())
  await page.goto('/')
  await micButton(page, 'Start talking').click()
  await expect(page.getByRole('alert')).toContainText('Connection lost. Reconnecting… your transcript is safe.')
  await expect(status(page)).toContainText('OFFLINE')
})

test('a blocked microphone explains how to fix it', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('denied', 'NotAllowedError'))
  })
  await page.goto('/')
  await micButton(page, 'Start talking').click()
  await expect(page.getByRole('alert')).toContainText('Microphone is blocked.')
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
  await expect(micButton(page, 'Start talking')).toBeVisible()
})
