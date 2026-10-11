import { expect, test } from '@playwright/test'
import { status } from './helpers'

// Interface fixes from the hosted-demo review: what a first-time visitor sees.

test('the access-code page explains TalkBack and offers the recorded demo', async ({ page }) => {
  await page.route('**/api/session', (route) => route.fulfill({ status: 401, json: { detail: 'access_code_required' } }))
  await page.goto('/')
  await expect(page.getByText('TalkBack is a voice assistant you can interrupt.')).toBeVisible()
  await page.getByRole('link', { name: 'Watch the recorded demo' }).click()
  await expect(page).toHaveURL(/\?replay/)
  await expect(page.locator('header').getByText('Recorded demo', { exact: true })).toBeVisible()
})

test('onboarding can be skipped or swapped for the recorded demo', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Talk to me like a person.' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Try recorded demo' })).toHaveAttribute('href', '?replay')

  await page.getByRole('button', { name: 'Set up later' }).click()
  await expect(page.getByText('Interrupt me any time.')).toBeVisible()
  await expect(status(page)).toContainText('READY')
  // Skipping never asked for the microphone, and the welcome does not come back.
  await page.reload()
  await expect(page.getByText('Interrupt me any time.')).toBeVisible()
})

test('the empty conversation suggests what to say', async ({ page }) => {
  await page.goto('/?state=idle')
  await expect(page.getByText('Try saying')).toBeVisible()
  await page.getByRole('button', { name: 'Remember a preference' }).click()
  await expect(page.getByText('Say: “Remember that I like short answers.”')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remember a preference' })).toHaveAttribute('aria-pressed', 'true')
})

test('in the recorded demo, skills explain they need a live conversation', async ({ page }) => {
  await page.goto('/?replay')
  await page.getByRole('button', { name: 'Skills' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Skills' })
  await expect(panel.getByText('Sample data. Start a live conversation to see yours.')).toBeVisible()
  await expect(panel.getByText('Skills run in a live conversation.')).toBeVisible()
  await expect(panel.getByRole('button', { name: /^Run / })).toHaveCount(0)
  await expect(panel.getByText('It does not send alerts yet.', { exact: false })).toBeVisible()
})

test('settings use plain tool names, show the running engine and hide model IDs', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Settings' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Settings' })
  await expect(panel.getByText('Read saved memories')).toBeVisible()
  await expect(panel.getByText('Delete saved memories')).toBeVisible()
  await expect(panel.getByText('memory_read')).toHaveCount(0)

  await expect(panel.getByText('Running now')).toBeVisible()
  await expect(panel.getByText('Full-duplex: off.', { exact: false })).toBeVisible()
  const planner = panel.getByLabel('Planner model')
  await expect(planner).toBeHidden()
  await panel.getByText('Advanced: models and providers').click()
  await expect(planner).toBeVisible()

  await expect(panel.getByText('Default: off · Now: off').first()).toBeVisible()
  await panel.getByRole('switch', { name: 'Show transcripts in logs' }).click({ force: true })
  await expect(panel.getByText('Default: off · Now: on')).toBeVisible()
})

test('approving the delete in the recorded demo removes it from the sample memory', async ({ page }) => {
  await page.goto('/?replay&speed=8')
  await page.getByRole('button', { name: 'Start talking' }).first().click()
  const card = page.getByRole('alertdialog')
  await expect(card).toBeVisible({ timeout: 15_000 })
  await card.getByRole('button', { name: 'Yes, do it' }).click()
  await expect(page.getByText('Memory deleted')).toBeVisible()
  await page.getByRole('button', { name: 'Memory' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Memory' })
  await expect(panel.getByText('Prefers Celsius')).toBeVisible()
  await expect(panel.getByText('Home city is Lisbon')).toHaveCount(0)
})

test('recording your voice is a choice kept in this browser', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Settings' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Settings' })
  await panel.getByRole('switch', { name: 'Save recordings on this device' }).click({ force: true })
  expect(await page.evaluate(() => localStorage.getItem('talkback.effects'))).toContain('"saveRecordings":true')
})
