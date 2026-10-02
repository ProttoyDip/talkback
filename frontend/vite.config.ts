import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, searchForWorkspaceRoot } from 'vite'

// The end-to-end tests point this at their own backend (playwright.config.ts).
const BACKEND = process.env.TALKBACK_BACKEND ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Same-origin in development: the backend checks the WebSocket Origin
    // and needs no CORS (SECURITY.md T7).
    proxy: {
      '/api': BACKEND,
      '/health': BACKEND,
      '/ws': { target: BACKEND, ws: true },
    },
    fs: {
      // The replay mode and tests read the shared fixture from docs/fixtures.
      allow: [searchForWorkspaceRoot(process.cwd()), '../docs/fixtures'],
    },
  },
})
