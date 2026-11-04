import { defineConfig } from '@playwright/test'
import base from './playwright.config.ts'

export default defineConfig({
  ...base,
  testDir: './tests/transfer-mock',
  projects: base.projects?.filter(p => p.name === 'laptop'),
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5272 --strictPort',
    url: 'http://127.0.0.1:5272/login',
    reuseExistingServer: false,
    env: { VITE_API_MOCK: 'true', VITE_SHARED_DEVICE_MOCK: 'false', VITE_GUARDIAN_TRANSFER_ENABLED: 'true' },
    timeout: 60_000,
  },
  use: { ...base.use, baseURL: 'http://127.0.0.1:5272' },
})
