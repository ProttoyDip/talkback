import { expect, test } from '@playwright/test'

// Plan P4: where memories came from, suggestions that wait for an OK,
// and an action history with Undo. Sample data (?mock).

test('a suggestion from TalkBack waits until you keep it', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Memory' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Memory' })
  const card = panel.getByRole('listitem').filter({ hasText: 'Likes jazz while working' })
  await expect(card).toContainText('Suggested by TalkBack. Not used until you keep it.')
  await card.getByRole('button', { name: 'Keep' }).click()
  await expect(card.getByRole('button', { name: 'Keep' })).toHaveCount(0)
  await expect(panel.getByText('You said: “Remember that I prefer Celsius.”')).toBeVisible()
})

test('the activity list undoes a change', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Memory' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Memory' })
  await panel.getByRole('tab', { name: 'Activity' }).click()
  await expect(panel.getByRole('tab', { name: 'Activity' })).toHaveAttribute('aria-selected', 'true')
  const action = panel.getByRole('listitem').filter({ hasText: 'Remembered “Prefers Celsius”' })
  await action.getByRole('button', { name: /^Undo/ }).click()
  await expect(action).toContainText('Undone')
  await expect(action.getByRole('button', { name: /^Undo/ })).toHaveCount(0)
})

test('replaced memories show only when asked', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Memory' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Memory' })
  await expect(panel.getByRole('switch', { name: 'Show replaced memories' })).not.toBeChecked()
})
