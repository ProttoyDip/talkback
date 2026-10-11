import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { expectNoHorizontalScroll } from './helpers'

// Plan P8: documents and research projects (sample data, ?mock), and cited
// passages under a tool chip (the server is faked).

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('talkback.onboarded', '1'))
})

test('documents: the list, an upload, and a delete', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.keyboard.press('m')
  const panel = page.getByRole('complementary', { name: 'Memory' })
  await panel.getByRole('tab', { name: 'Documents' }).click()
  const list = panel.getByRole('list', { name: 'Your documents' })
  await expect(list.getByRole('listitem')).toHaveCount(2)
  await expect(list).toContainText('PDF · 9 pages')
  await panel.getByLabel('Add a document').setInputFiles({
    name: 'Packing list.md', mimeType: 'text/markdown', buffer: Buffer.from('# Pack\n- passport'),
  })
  await expect(list.getByRole('listitem')).toHaveCount(3)
  await expect(list.getByRole('listitem').first()).toContainText('Packing list')
  await panel.getByRole('button', { name: 'Delete document: Packing list' }).click()
  await expect(list.getByRole('listitem')).toHaveCount(2)
})

test('projects: notes with their sources, and deleting asks first', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.keyboard.press('m')
  const panel = page.getByRole('complementary', { name: 'Memory' })
  await panel.getByRole('tab', { name: 'Projects' }).click()
  await panel.getByRole('button', { name: /^Heat pumps/ }).click()
  const notes = panel.getByRole('list', { name: 'Notes in Heat pumps' })
  await expect(notes.getByRole('listitem').first()).toContainText('-20 °C')
  await expect(notes.getByRole('link', { name: /Energy Saving Trust/ })).toHaveAttribute('target', '_blank')
  await panel.getByLabel('New project').fill('Bikes')
  await panel.getByRole('button', { name: 'Create' }).click()
  await expect(panel.getByRole('list', { name: 'Your projects' })).toContainText('Bikes')
  await panel.getByRole('button', { name: 'Delete project: Bikes' }).click()
  await expect(panel.getByRole('alert')).toContainText("can't be undone")
  await panel.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(panel.getByRole('list', { name: 'Your projects' })).not.toContainText('Bikes')
})

test('a document answer shows the passages it used', async ({ page, isMobile }) => {
  test.skip(isMobile, 'one run is enough for a faked server')
  await page.route('**/api/session', (route) =>
    route.fulfill({ json: { token: 't', expires_at: Math.floor(Date.now() / 1000) + 900, user: { id: 'local', anonymous: false } } }),
  )
  await page.route('**/api/settings', (route) => route.fulfill({ json: { timezone: 'UTC' } }))
  await page.route('**/api/reminders**', (route) => route.fulfill({ json: { items: [] } }))
  await page.routeWebSocket('**/ws/session**', (ws) => {
    const send = (event: object) => ws.send(JSON.stringify(event))
    ws.onMessage((message) => {
      if (typeof message !== 'string') return
      const event = JSON.parse(message)
      if (event.type === 'session.start') send({ type: 'state', state: 'idle' })
      if (event.type === 'text.input') {
        send({ type: 'transcript.delta', message_id: 'u1', speaker: 'user', text: event.text, final: true, typed: true })
        send({ type: 'transcript.delta', message_id: 'a1', speaker: 'assistant', text: 'Pets need written permission.', final: true })
        send({
          type: 'tool.status', call_id: 'c1', message_id: 'a1', name: 'docs_search', status: 'done', undoable: false, sources: [],
          citations: [{ kind: 'document', id: 'd1', title: 'Apartment lease', locator: 'page 4', quote: 'No pets without the landlord’s written consent.' }],
        })
      }
    })
  })
  await page.goto('/')
  await page.getByLabel('Type instead').fill('What does my lease say about pets?')
  await page.getByRole('button', { name: 'Send' }).click()
  const chip = page.getByRole('button', { name: '1 passage' })
  await chip.click()
  await expect(page.getByText('Apartment lease')).toBeVisible()
  await expect(page.getByText('· page 4')).toBeVisible()
  await expect(page.getByText('No pets without the landlord’s written consent.')).toBeVisible()
})

for (const tab of ['Documents', 'Projects']) {
  test(`${tab} tab has no WCAG 2.2 AA violations and fits 375 px`, async ({ page }) => {
    await page.goto('/?state=idle&mock')
    await page.keyboard.press('m')
    const panel = page.getByRole('complementary', { name: 'Memory' })
    await panel.getByRole('tab', { name: tab }).click()
    if (tab === 'Projects') await panel.getByRole('button', { name: /^Heat pumps/ }).click()
    await expect(panel.getByRole('list').first()).toBeVisible()
    await page.waitForTimeout(500) // let the drawer finish sliding in
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze()
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`)).toEqual([])
    await expectNoHorizontalScroll(page)
  })
}
