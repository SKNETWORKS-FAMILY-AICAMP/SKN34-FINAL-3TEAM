import { defineConfig, devices } from '@playwright/test'
process.env.E2E_POSTGRES_CONTAINER ??= 'guardian-transfer-289-postgres-1'

export default defineConfig({
  testDir: './tests/transfer-local', workers: 1, fullyParallel: false, timeout: 120_000,
  reporter: [['list'], ['json', { outputFile: 'test-results/transfer-local-results.json' }]],
  use: { ...devices['Desktop Chrome'], baseURL: process.env.TRANSFER_WEB_ORIGIN || 'http://127.0.0.1:5195', viewport: { width: 1360, height: 980 },
    screenshot: 'only-on-failure', trace: 'retain-on-failure', launchOptions: { executablePath: process.env.CHROME_PATH || undefined } },
})
