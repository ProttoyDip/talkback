import { expect, test } from '@playwright/test'

// Plan P6: the plan card. The server is faked: session, WebSocket and plan routes.
test.skip(({ isMobile }) => isMobile, 'one run is enough for a faked server')

test('a day plan: pick blocks, add them, undo', async ({ page }) => {
  const applied: unknown[] = []
  await page.addInitScript(() => localStorage.setItem('talkback.onboarded', '1'))
  await page.route('**/api/session', (route) =>
    route.fulfill({ json: { token: 't', expires_at: Math.floor(Date.now() / 1000) + 900, user: { id: 'local', anonymous: false } } }),
  )
  await page.route('**/api/settings', (route) => route.fulfill({ json: { timezone: 'UTC' } }))
  await page.route('**/api/reminders**', (route) => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/plans/p1/apply', (route) => {
    applied.push(route.request().postDataJSON())
    return route.fulfill({ json: { proposal_id: 'p1', status: 'accepted', applied: [1], action_id: 'a1' } })
  })
  let undone = false
  await page.route('**/api/actions/a1/undo', (route) => {
    undone = true
    return route.fulfill({ json: { id: 'a1', tool: 'day_plan_apply', status: 'undone', summary: 'x', created_at: '', undoable: false } })
  })
  await page.routeWebSocket('**/ws/session**', (ws) => {
    ws.onMessage((message) => {
      if (typeof message !== 'string' || !message.includes('text.input')) return
      const send = (event: object) => ws.send(JSON.stringify(event))
      send({ type: 'transcript.delta', message_id: 'u1', speaker: 'user', text: 'Prepare my day.', final: true, typed: true })
      send({ type: 'transcript.delta', message_id: 'a1', speaker: 'assistant', text: 'Here is a plan.', final: true })
      send({
        type: 'plan.proposed', proposal_id: 'p1', message_id: 'a1', date: '2030-01-07', expires_at: '2030-01-07T10:00:00Z',
        items: [
          { index: 0, op: 'create_block', title: 'Invoice', starts_at: '2030-01-07T09:00:00Z', ends_at: '2030-01-07T10:00:00Z', reason: 'Due today' },
          { index: 1, op: 'create_block', title: 'Slides', starts_at: '2030-01-07T10:00:00Z', ends_at: '2030-01-07T11:30:00Z', reason: 'High priority' },
        ],
      })
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Prepare my day' }).click()
  const card = page.getByRole('region', { name: '2 blocks for your most urgent tasks' })
  await expect(card).toContainText('Due today')
  await card.getByRole('checkbox', { name: /Invoice/ }).uncheck()
  await card.getByRole('button', { name: 'Add 1 block' }).click()
  await expect(card).toContainText('Added to your calendar.')
  expect(applied).toEqual([{ items: [1] }])
  await card.getByRole('button', { name: 'Undo' }).click()
  await expect(card).toContainText('Undone.')
  expect(undone).toBe(true)
})
