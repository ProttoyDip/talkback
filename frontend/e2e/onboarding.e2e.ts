import { expect, test } from '@playwright/test'

test('first run walks through welcome, microphone and privacy', async ({ page, context }) => {
  await context.grantPermissions(['microphone'])
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Talk to me like a person.' })).toBeVisible()
  await page.getByRole('button', { name: 'Allow microphone' }).click()
  await expect(page.getByRole('heading', { name: 'I need your microphone.' })).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('heading', { name: 'Your words stay yours.' })).toBeVisible()
  await page.getByRole('button', { name: 'Start talking' }).click()
  await expect(page.getByText('Use headphones for the best interruptions.')).toBeVisible()
  await page.getByRole('button', { name: 'Got it' }).click()
  await expect(page.getByText('Use headphones for the best interruptions.')).toBeHidden()

  // It shows only once.
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Talk to me like a person.' })).toBeHidden()
})

test('a blocked microphone shows how to allow it', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('no', 'NotAllowedError'))
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Allow microphone' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByRole('alert')).toContainText('Microphone is blocked')
})
