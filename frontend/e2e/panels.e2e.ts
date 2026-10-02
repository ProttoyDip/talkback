import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { expectNoHorizontalScroll } from './helpers'

// Panels run on the local sample data (?mock), so they need no backend routes.

test('memory panel searches, edits and forgets', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Memory' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Memory' })
  await expect(panel.getByText('Prefers Celsius')).toBeVisible()
  await expect(panel.getByText('You said: “Remember that I prefer Celsius.”')).toBeVisible()

  await panel.getByRole('searchbox').fill('short')
  await expect(panel.getByText('Likes short answers')).toBeVisible()
  await expect(panel.getByText('Prefers Celsius')).toBeHidden()
  await panel.getByRole('searchbox').fill('')

  await panel.getByRole('button', { name: 'Edit memory: Likes short answers' }).click()
  await panel.getByLabel('Edit memory').fill('Likes very short answers')
  await panel.getByRole('button', { name: 'Save' }).click()
  await expect(panel.getByText('Likes very short answers')).toBeVisible()

  await panel.getByRole('button', { name: 'Forget everything' }).click()
  await panel.getByRole('button', { name: 'Yes, forget everything' }).click()
  await expect(panel.getByText('Nothing remembered yet.')).toBeVisible()
})

test('skills panel lists skills; Run needs an open session', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Skills' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Skills' })
  await expect(panel.getByRole('heading', { name: 'Morning brief' })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Run Morning brief' })).toBeDisabled()
})

test('settings panel toggles a tool and shows models', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Settings' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Settings' })
  const weather = panel.getByRole('switch', { name: 'Weather' })
  await expect(weather).toBeChecked()
  await weather.click({ force: true })
  await expect(weather).not.toBeChecked()
  await expect(panel.getByLabel('Planner model')).toHaveValue('nebius:nemotron-3-nano')
  await expect(panel.getByRole('switch', { name: 'Save recordings on this device' })).not.toBeChecked()
})

test('a panel without server support shows a plain error and a retry', async ({ page }) => {
  await page.route('**/api/settings', (route) => route.fulfill({ status: 404, body: '{}' }))
  await page.route('**/api/session', (route) =>
    route.fulfill({ json: { token: 't', expires_at: Math.floor(Date.now() / 1000) + 900 } }),
  )
  await page.goto('/?state=idle')
  await page.getByRole('button', { name: 'Settings' }).first().click()
  await expect(page.getByText('The server does not offer this yet.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
})

for (const name of ['Memory', 'Skills', 'Settings']) {
  test(`${name} panel has no WCAG 2.2 AA violations and fits 375 px`, async ({ page }) => {
    await page.goto('/?state=idle&mock')
    await page.getByRole('button', { name }).first().click()
    await expect(page.getByRole('complementary', { name })).toBeVisible()
    await page.waitForTimeout(500) // let the drawer finish sliding in
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze()
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`)).toEqual([])
    await expectNoHorizontalScroll(page)
  })
}
