import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url),
  { chromium } = require('playwright'),
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
  })
const p = await browser.newPage(),
  paths = [],
  errors = []
p.on('pageerror', (e) => errors.push(e.message))
try {
  await p.route('**/api/v1/**', (route) => {
    paths.push(new URL(route.request().url()).pathname)
    return route.fulfill({
      status: 404,
      contentType: 'application/problem+json',
      body: JSON.stringify({
        status: 404,
        code: 'NOT_FOUND',
        title: '실제 API 경로 확인용 404 응답 스텁',
        retryable: false,
      }),
    })
  })
  await p.goto((process.env.API_URL ?? 'http://127.0.0.1:5174') + '/login')
  await p.getByLabel('이메일', { exact: true }).fill('parent@example.test')
  await p.getByLabel('비밀번호', { exact: true }).fill('test-password')
  await p.getByRole('button', { name: '로그인', exact: true }).click()
  await p.getByText('NOT_FOUND', { exact: true }).waitFor()
  assert.ok(paths.includes('/api/v1/auth/login'))
  assert.ok(paths.includes('/api/v1/auth/refresh'))
  assert.equal(await p.getByLabel('상태 시연', { exact: true }).count(), 0)
  assert.equal(await p.getByRole('heading', { name: '서윤의 기록을 함께 살펴보세요.' }).count(), 0)
  assert.equal(
    await p.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length),
    0,
  )
  assert.deepEqual(errors, [])
  console.log(
    JSON.stringify(
      {
        passed: true,
        paths,
        pageErrors: errors,
        realBackendIntegration: false,
        note: '운영 API 모드 경로·오류 UI만 검증. 응답은 404 스텁.',
      },
      null,
      2,
    ),
  )
} finally {
  await browser.close()
}
