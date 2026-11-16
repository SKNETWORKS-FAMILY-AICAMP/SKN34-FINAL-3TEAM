import { defineConfig, devices } from '@playwright/test'

/** 운영 빌드와 합성 HttpOnly 쿠키로 로그인 유지·복구를 검증한다. */
export default defineConfig({
  testDir: './tests/auth-browser', workers: 1, retries: 0, timeout: 30_000,
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:5279', serviceWorkers: 'block',
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
    launchOptions: { executablePath: process.env.CHROME_PATH || undefined } },
  webServer: { command: 'npm run preview -- --host 127.0.0.1 --port 5279 --strictPort',
    url: 'http://127.0.0.1:5279/login', reuseExistingServer: false, timeout: 30_000 },
})
