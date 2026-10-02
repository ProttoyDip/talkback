import path from 'node:path'
import { defineConfig } from '@playwright/test'

/*
 * End-to-end tests. They drive the installed Microsoft Edge (no browser
 * download) with a fake microphone that plays a test tone. They start their
 * own backend (port 8001, no voice engine, no keys) and dev server (port
 * 5174), so they never depend on your local .env or running servers.
 *   npm run e2e
 */
const python = path.join('.venv', process.platform === 'win32' ? 'Scripts' : 'bin', 'python')

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  fullyParallel: true,
  retries: 0,
  reporter: [['list']],
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:5174',
    channel: 'msedge',
    permissions: ['microphone'],
    launchOptions: {
      args: [
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
        '--autoplay-policy=no-user-gesture-required',
      ],
    },
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1280, height: 800 } } },
    {
      name: 'mobile',
      use: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
    },
  ],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --port 8001 --ws-max-size 65536`,
      cwd: '../backend',
      url: 'http://localhost:8001/health',
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VOICE_ENGINE: 'none', ALLOWED_ORIGINS: 'http://localhost:5174' },
    },
    {
      command: 'npm run dev -- --port 5174 --strictPort',
      url: 'http://localhost:5174',
      reuseExistingServer: false,
      timeout: 60_000,
      env: { TALKBACK_BACKEND: 'http://localhost:8001' },
    },
  ],
})
