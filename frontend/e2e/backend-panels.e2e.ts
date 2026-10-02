import { expect, test } from '@playwright/test'

// The panels against the real backend routes (no ?mock).
test.describe.configure({ mode: 'serial' })
test.skip(({ isMobile }) => isMobile, 'real backend checks run once, on desktop')

test('skills come from the backend and Run waits for a conversation', async ({ page }) => {
  await page.goto('/?state=idle')
  await page.getByRole('button', { name: 'Skills' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Skills' })
  await expect(panel.getByRole('heading', { name: 'Morning brief' })).toBeVisible()
  await expect(panel.getByRole('heading', { name: 'Quick research' })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Run Morning brief' })).toBeDisabled()
})

test('settings save to the backend and survive a reload', async ({ page }) => {
  await page.goto('/?state=idle')
  await page.getByRole('button', { name: 'Settings' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Settings' })
  const recordings = panel.getByRole('switch', { name: 'Save recordings on this device' })
  await expect(recordings).not.toBeChecked()
  await recordings.click({ force: true })
  await expect(recordings).toBeChecked()

  await page.reload()
  await page.getByRole('button', { name: 'Settings' }).first().click()
  const again = page.getByRole('complementary', { name: 'Settings' })
  await expect(again.getByRole('switch', { name: 'Save recordings on this device' })).toBeChecked()

  // Put it back, so the next run starts from the private default.
  await again.getByRole('switch', { name: 'Save recordings on this device' }).click({ force: true })
  await expect(again.getByRole('switch', { name: 'Save recordings on this device' })).not.toBeChecked()
})
