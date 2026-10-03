import { expect, test } from '@playwright/test'

// The animated background is off in automated browsers unless the URL has ?bg.
test('the animated background starts without errors and stays behind the content', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (message) => message.type() === 'error' && errors.push(message.text()))
  page.on('pageerror', (error) => errors.push(String(error)))
  await page.goto('/?state=assistant_speaking&bg')
  const canvas = page.locator('canvas[aria-hidden="true"].fixed')
  await expect(canvas).toHaveCount(1)
  await page.waitForTimeout(2500) // let the scene load and draw
  const box = await canvas.boundingBox()
  expect(box?.width).toBeGreaterThan(300)
  // Content stays usable on top of it.
  await expect(page.getByRole('region', { name: 'Transcript' })).toBeVisible()
  await page.getByRole('button', { name: 'Memory' }).first().click()
  await expect(page.getByRole('complementary', { name: 'Memory' })).toBeVisible()
  expect(errors).toEqual([])
})

test('no background in automated runs by default', async ({ page }) => {
  await page.goto('/?state=idle')
  // The canvas element exists but nothing is drawn: it has the default 300x150 size.
  const size = await page.locator('canvas[aria-hidden="true"].fixed').evaluate((c: HTMLCanvasElement) => c.width)
  expect(size).toBe(300)
})
