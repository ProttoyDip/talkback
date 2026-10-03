import { expect, test } from '@playwright/test'

test('Stop shows only while TalkBack is answering', async ({ page }) => {
  await page.goto('/?state=assistant_speaking')
  await expect(page.getByRole('button', { name: /Stop/ })).toBeVisible()
  await page.goto('/?state=idle')
  await expect(page.getByRole('button', { name: /Stop/ })).toBeHidden()
})

test('Esc closes an open panel before anything else', async ({ page }) => {
  await page.goto('/?state=assistant_speaking')
  await page.keyboard.press('m')
  await expect(page.getByRole('complementary', { name: 'Memory' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('complementary', { name: 'Memory' })).toBeHidden()
  await expect(page.getByRole('button', { name: /Stop/ })).toBeVisible()
})

test('visual effects switches are remembered in this browser', async ({ page }) => {
  await page.goto('/?state=idle&mock')
  await page.getByRole('button', { name: 'Settings' }).first().click()
  const panel = page.getByRole('complementary', { name: 'Settings' })
  const background = panel.getByRole('switch', { name: 'Animated background' })
  await expect(background).toBeChecked()
  await background.click({ force: true })
  await expect(background).not.toBeChecked()
  expect(await page.evaluate(() => localStorage.getItem('talkback.effects'))).toContain('"background":false')
})

test('a demo with an access code asks for it first', async ({ page }) => {
  await page.route('**/api/session', (route) => {
    const ok = route.request().headers()['x-access-code'] === 'demo-code'
    return ok
      ? route.fulfill({ json: { token: 't', expires_at: Math.floor(Date.now() / 1000) + 900 } })
      : route.fulfill({ status: 401, json: { detail: 'access_code_required' } })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'This demo needs an access code.' })).toBeVisible()
  await page.getByLabel('Access code').fill('wrong')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('alert')).toContainText("That code didn't work")
  await page.getByLabel('Access code').fill('demo-code')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Talk to me like a person.' })).toBeVisible()
})
