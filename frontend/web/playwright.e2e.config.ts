import { defineConfig, devices } from '@playwright/test'

// 실서버 E2E (#246): compose.e2e.yaml 스택(core·learning·ai·report + 스텁)이 먼저 떠 있어야 함.
// MSW 화면 테스트(playwright.config.ts)와 webServer 설정이 달라 파일을 분리한다.
const origin = 'http://127.0.0.1:5272' // infrastructure/stubs/e2e.env AUTH_WEB_ORIGIN과 같아야 함

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 180_000,
  expect: { timeout: 30_000 },
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: origin,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { executablePath: process.env.CHROME_PATH || undefined },
  },
  projects: [{ name: 'e2e', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5272 --strictPort',
    url: `${origin}/login`,
    reuseExistingServer: !process.env.CI,
    // 결제수단 버튼 활성 조건(test_gck_)만 맞춘 가짜 키. 토스 SDK 스크립트는 테스트에서 차단
    env: {
      VITE_API_MOCK: 'false',
      VITE_SHARED_DEVICE_MOCK: 'false',
      TOSSPAYMENTS_CLIENT_KEY: 'test_gck_e2e_stub_only',
      TOSS_TEST_BILLING_CLIENT_KEY: 'test_ck_e2e_stub_only',
    },
    timeout: 60_000,
  },
})
