import { expect, test } from '@playwright/test'

// Plan P7: continue an unfinished conversation. The server is faked.
test.skip(({ isMobile }) => isMobile, 'one run is enough for a faked server')

test('continue where you left off', async ({ page }) => {
  const answers: unknown[] = []
  await page.addInitScript(() => localStorage.setItem('talkback.onboarded', '1'))
  await page.route('**/api/session', (route) =>
    route.fulfill({ json: { token: 't', expires_at: Math.floor(Date.now() / 1000) + 900, user: { id: 'local', anonymous: false } } }),
  )
  await page.route('**/api/settings', (route) => route.fulfill({ json: { timezone: 'UTC' } }))
  await page.route('**/api/reminders**', (route) => route.fulfill({ json: { items: [] } }))
  await page.routeWebSocket('**/ws/session**', (ws) => {
    ws.onMessage((message) => {
      if (typeof message !== 'string') return
      const event = JSON.parse(message)
      if (event.type === 'session.start') {
        ws.send(JSON.stringify({ type: 'state', state: 'idle' }))
        ws.send(JSON.stringify({
          type: 'session.resumable', state_id: 's1', goal: 'Help me plan tomorrow', updated_at: '2030-01-07T10:00:00Z',
          decisions: ['Added the task “Call mom”'], pending: ['Waiting for your OK: Delete the task “Gym”?'],
        }))
      }
      if (event.type === 'session.resume') answers.push(event)
    })
  })
  await page.goto('/')
  await page.getByLabel('Type instead').fill('Hi')
  await page.getByRole('button', { name: 'Send' }).click()
  const banner = page.getByRole('region', { name: /Continue where you left off/ })
  await expect(banner).toContainText('Help me plan tomorrow')
  await expect(banner).toContainText('Still open (TalkBack will ask again)')
  await banner.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByText('Continuing. TalkBack will check anything still open with you first.')).toBeVisible()
  expect(answers).toEqual([{ type: 'session.resume', state_id: 's1', accept: true }])
})
