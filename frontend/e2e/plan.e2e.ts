import { expect, test } from '@playwright/test'

// Plan P5: tasks, calendar, reminders and your own skills. Sample data (?mock).

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('talkback.onboarded', '1'))
})

test('tasks: add one, then complete it', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Plan' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Plan' })
  await expect(panel.getByText('Send the slides to Mira')).toBeVisible()
  await panel.getByLabel('New task').fill('Buy milk')
  await panel.getByRole('button', { name: 'Add task' }).click()
  await expect(panel.getByText('Buy milk')).toBeVisible()
  await panel.getByRole('button', { name: 'Done: Buy milk' }).click()
  await expect(panel.getByText('Buy milk')).toHaveCount(0)
})

test('calendar: the day as a list, and a new block', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.keyboard.press('p')
  const panel = page.getByRole('complementary', { name: 'Plan' })
  await panel.getByRole('tab', { name: 'Calendar' }).click()
  const agenda = panel.getByRole('list', { name: 'Agenda' })
  await expect(agenda.getByRole('listitem')).toHaveCount(2)
  await panel.getByLabel('New block').fill('Lunch')
  await panel.getByLabel('From', { exact: true }).fill('12:00')
  await panel.getByLabel('To', { exact: true }).fill('13:00')
  await panel.getByRole('button', { name: 'Add block' }).click()
  await expect(agenda.getByRole('listitem')).toHaveCount(3)
  await expect(agenda.getByRole('listitem').nth(1)).toContainText('Lunch')
})

test('a due reminder stays until you answer it', async ({ page }) => {
  const answered: string[] = []
  await page.route('**/api/session', (route) =>
    route.fulfill({ json: { token: 't', expires_at: Math.floor(Date.now() / 1000) + 900, user: { id: 'local', anonymous: false } } }),
  )
  await page.route('**/api/settings', (route) => route.fulfill({ json: { timezone: 'UTC' } }))
  await page.route('**/api/reminders**', (route) => {
    const url = route.request().url()
    if (route.request().method() === 'POST') {
      answered.push(url.split('/').at(-1) ?? '')
      return route.fulfill({ json: {} })
    }
    return route.fulfill({
      json: {
        items: [{ id: 'r9', text: 'Stretch', due_at: new Date(Date.now() - 5_000).toISOString(), status: 'scheduled', snooze_count: 0, created_at: '2026-10-10T09:00:00Z' }],
      },
    })
  })
  await page.goto('/')
  const reminder = page.getByRole('list', { name: 'Reminders' }).getByRole('alert')
  await expect(reminder).toContainText('Stretch')
  await reminder.getByRole('button', { name: 'Snooze 10 min' }).click()
  await expect(reminder).toHaveCount(0)
  expect(answered).toEqual(['delivered', 'snooze'])
})

test('make your own skill, turn it off, delete it', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Skills' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Skills' })
  await panel.getByRole('button', { name: 'Make your own skill' }).click()
  const form = panel.getByRole('form', { name: 'New skill' })
  await form.getByLabel('Name').fill('Evening wrap')
  await form.getByLabel('Say').fill('wrap up my day')
  await form.getByLabel('Read tasks').check()
  await form.getByLabel('What TalkBack does').fill('List my open tasks briefly.')
  await form.getByRole('button', { name: 'Make skill' }).click()
  const card = panel.getByRole('listitem').filter({ hasText: 'Evening wrap' }).first()
  await expect(card).toContainText('Yours')
  await card.getByRole('button', { name: 'Turn off' }).click()
  await expect(card).toContainText('Off')
  await card.getByRole('button', { name: 'Delete skill: Evening wrap' }).click()
  await expect(panel.getByText('Evening wrap')).toHaveCount(0)
  // Built-ins can be copied, not edited.
  const builtin = panel.getByRole('listitem').filter({ hasText: 'Morning brief' }).first()
  await expect(builtin.getByRole('button', { name: /^Edit skill/ })).toHaveCount(0)
  await builtin.getByRole('button', { name: 'Make a copy' }).click()
  await expect(panel.getByLabel('Name')).toHaveValue('Morning brief (mine)')
})
