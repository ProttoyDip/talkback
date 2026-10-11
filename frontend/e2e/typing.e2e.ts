import { expect, test } from '@playwright/test'

// Plan P3: type instead of talking. The test backend has no voice engine,
// so it only echoes the typed turn.
test.describe.configure({ mode: 'serial' })
test.skip(({ isMobile }) => isMobile, 'live backend checks run once, on desktop')

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('talkback.onboarded', '1')
    // Typing must work with no microphone at all.
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('denied', 'NotAllowedError'))
  })
})

test('typing starts a conversation without the microphone', async ({ page }) => {
  const sent: string[] = []
  page.on('websocket', (ws) => ws.on('framesent', ({ payload }) => typeof payload === 'string' && sent.push(payload)))
  await page.goto('/')
  await page.getByLabel('Type instead').fill('What is full-duplex?')
  await page.getByRole('button', { name: 'Send' }).click()

  const turn = page.getByRole('listitem').filter({ hasText: 'What is full-duplex?' })
  await expect(turn).toBeVisible()
  await expect(turn).toContainText('typed')
  expect(sent).toContainEqual(JSON.stringify({ type: 'text.input', text: 'What is full-duplex?' }))
  await expect(page.getByRole('alert')).toHaveCount(0) // no "Microphone is blocked"
  await expect(page.getByLabel('Type instead')).toHaveValue('')
})

test('an example chip sends its words', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Remember a preference' }).click()
  await expect(page.getByRole('listitem').filter({ hasText: 'Remember that I like short answers.' })).toBeVisible()
})
