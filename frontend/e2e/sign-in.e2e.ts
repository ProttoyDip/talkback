import { expect, test, type Page } from '@playwright/test'

// Accounts (plan P2). The server and Supabase Auth are faked with routes.
const SUPABASE = 'https://project.supabase.test'

async function accountsOn(page: Page) {
  await page.addInitScript(() => localStorage.setItem('talkback.onboarded', '1'))
  await page.route('**/api/auth-config', (route) =>
    route.fulfill({ json: { mode: 'required', supabase_url: SUPABASE, publishable_key: 'pk', access_code: true } }),
  )
  await page.route('**/api/session', (route) => {
    const headers = route.request().headers()
    if (headers['x-access-code'] !== 'demo-code') {
      return route.fulfill({ status: 401, json: { detail: 'access_code_required' } })
    }
    if (headers.authorization !== 'Bearer guest-token') {
      return route.fulfill({ status: 401, json: { detail: 'sign_in_required' } })
    }
    return route.fulfill({
      json: {
        token: 't',
        expires_at: Math.floor(Date.now() / 1000) + 900,
        user: { id: 'guest-1', email: null, anonymous: true },
      },
    })
  })
}

test('with accounts on, the first screen offers email sign-in, a guest pass and the recorded demo', async ({
  page,
}) => {
  await accountsOn(page)
  let otp: Record<string, unknown> | undefined
  await page.route(`${SUPABASE}/auth/v1/otp**`, (route) => {
    otp = route.request().postDataJSON()
    return route.fulfill({ json: {} })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Sign in to talk.' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Watch the recorded demo' })).toBeVisible()

  // The code comes first: without it, neither way in is enabled.
  await page.getByLabel('Email').fill('ada@example.com')
  await expect(page.getByRole('button', { name: 'Send sign-in link' })).toBeDisabled()
  await page.getByLabel('Access code').fill('demo-code')
  await page.getByRole('button', { name: 'Send sign-in link' }).click()
  await expect(page.getByRole('status')).toContainText('Check your email.')
  expect(otp?.email).toBe('ada@example.com')
})

test('a guest with the right code gets in', async ({ page }) => {
  await accountsOn(page)
  await page.route(`${SUPABASE}/auth/v1/signup**`, (route) =>
    route.fulfill({
      json: {
        access_token: 'guest-token',
        token_type: 'bearer',
        expires_in: 3600,
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        refresh_token: 'refresh',
        user: { id: 'guest-1', aud: 'authenticated', role: 'authenticated', is_anonymous: true, app_metadata: {}, user_metadata: {}, created_at: '2026-10-11T00:00:00Z' },
      },
    }),
  )
  await page.goto('/')
  await page.getByLabel('Access code').fill('demo-code')
  await page.getByRole('button', { name: 'Continue as guest' }).click()
  await expect(page.getByText('Interrupt me any time.')).toBeVisible()
})
