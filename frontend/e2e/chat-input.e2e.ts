import { expect, test } from '@playwright/test'

// The prompt box: rests as one line, opens when used, Enter sends,
// Shift+Enter adds a line, "+" adds a document. The server is faked.
test.skip(({ isMobile }) => isMobile, 'one run is enough for a faked server')

test('typing, sending and adding a document', async ({ page }) => {
  const sent: string[] = []
  await page.addInitScript(() => localStorage.setItem('talkback.onboarded', '1'))
  await page.route('**/api/session', (route) =>
    route.fulfill({ json: { token: 't', expires_at: Math.floor(Date.now() / 1000) + 900, user: { id: 'local', anonymous: false } } }),
  )
  await page.route('**/api/settings', (route) => route.fulfill({ json: { timezone: 'UTC' } }))
  await page.route('**/api/reminders**', (route) => route.fulfill({ json: { items: [] } }))
  let listed = 0
  await page.route('**/api/documents', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 201, json: { id: 'd9', title: 'Lease', filename: 'Lease.pdf', kind: 'pdf', size_bytes: 9, chunks: 0, status: 'processing', created_at: '2026-10-12T00:00:00Z' } })
      : route.fulfill({ json: { items: [{ id: 'd9', title: 'Lease', filename: 'Lease.pdf', kind: 'pdf', size_bytes: 9, chunks: 3, pages: 1, status: ++listed > 0 ? 'ready' : 'processing', created_at: '2026-10-12T00:00:00Z' }] } }),
  )
  await page.routeWebSocket('**/ws/session**', (ws) => {
    ws.onMessage((message) => {
      if (typeof message !== 'string') return
      const event = JSON.parse(message)
      if (event.type === 'session.start') ws.send(JSON.stringify({ type: 'state', state: 'idle' }))
      if (event.type === 'text.input') sent.push(event.text)
    })
  })
  await page.goto('/')
  const box = page.getByLabel('Type instead')
  const send = page.getByRole('button', { name: 'Send' })
  await expect(send).toBeDisabled() // nothing to send yet
  await box.click()
  await expect(page.getByText('Enter to send · Shift+Enter for a new line')).toBeVisible()
  await box.pressSequentially('First line')
  await box.press('Shift+Enter')
  await box.pressSequentially('second line')
  await expect(box).toHaveValue('First line\nsecond line')
  await box.press('Enter')
  await expect.poll(() => sent).toEqual(['First line\nsecond line'])
  await expect(box).toHaveValue('')

  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    box.focus().then(() => page.getByRole('button', { name: /Add a document/ }).click()),
  ])
  await chooser.setFiles({ name: 'Lease.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') })
  const files = page.getByRole('list', { name: 'Added files' })
  await expect(files).toContainText('Lease')
  await expect(files).toContainText('Ready: ask about it', { timeout: 6000 })
  await files.getByRole('button', { name: 'Hide Lease' }).click()
  await expect(files).toHaveCount(0)
})
