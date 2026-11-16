import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './tests/model-browser', workers: 1, retries: 0, timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5277', serviceWorkers: 'block', screenshot: 'only-on-failure', trace: 'retain-on-failure', launchOptions: { executablePath: process.env.CHROME_PATH || undefined } },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'tablet', use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 1024 } } },
    { name: 'phone', use: { ...devices['Desktop Chrome'], viewport: { width: 390, height: 844 } } },
  ],
  webServer: { command: 'npm run preview -- --host 127.0.0.1 --port 5277 --strictPort', url: 'http://127.0.0.1:5277/admin/models', reuseExistingServer: false, timeout: 30_000 },
})
