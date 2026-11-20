import { test, expect } from '@playwright/test'

for (const role of ['parent', 'admin'] as const) {
  test(`${role} 목업은 현재 저장본과 이전 저장본 모두 새로고침 복원 (#837·#845)`, async ({ page }) => {
    await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
    await page.goto(role === 'admin' ? '/admin/login' : '/login')
    await page.getByRole('button', { name: role === 'admin' ? '로그인' : '시연 계정으로 로그인', exact: true }).click()
    await expect(page).toHaveURL(role === 'admin' ? /\/admin\/home/ : /\/parent\/journal/)
    for (const legacy of [false, true]) {
      await page.evaluate(old => {
        const key = 'sagomungchi:msw-fixture:v1'
        const raw = sessionStorage.getItem(key)
        if (!raw) throw new Error('저장된 시연 세션이 없습니다.')
        const snapshot = JSON.parse(raw)
        if (old) snapshot.reports = []
        sessionStorage.setItem(key, JSON.stringify(snapshot))
      }, legacy)
      await page.reload()
      await expect(page.getByRole('button', { name: '로그아웃', exact: true })).toBeVisible()
      await expect(page).toHaveURL(role === 'admin' ? /\/admin\/home/ : /\/parent\/journal/)
      await expect(page.getByRole('button', { name: '시연 계정으로 로그인', exact: true })).toHaveCount(0)
    }
  })
}
