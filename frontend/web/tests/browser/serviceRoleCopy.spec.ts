import { test, expect, type Page } from '@playwright/test'
import { waitForStudentHome } from './studentFixture.ts'

const navigate = (page: Page, path: string) => page.evaluate(path => {
  history.pushState({}, '', path)
  dispatchEvent(new PopStateEvent('popstate'))
}, path)

for (const role of ['parent', 'student'] as const) {
  test(`${role} support preserves role-specific copy and hides submission diagnostics @responsive`, async ({ page }, info) => {
    await page.addInitScript(() => {
      const original = window.fetch.bind(window)
      window.fetch = (input, init) => {
        const path = new URL(input instanceof Request ? input.url : String(input), location.href).pathname
        const method = init?.method ?? (input instanceof Request ? input.method : 'GET')
        if (path === '/api/v1/inquiries' && method === 'POST') {
          return Promise.resolve(Response.json({ status: 503, title: '문의를 접수하지 못했습니다.', detail: '잠시 뒤 다시 접수해 주세요.', code: 'SYNTHETIC_SUPPORT_FAILURE', traceId: 'synthetic-support-trace' }, { status: 503 }))
        }
        return original(input, init)
      }
    })
    if (role === 'student') {
      await page.goto('/student/login')
      await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
      await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
      for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
      await page.getByRole('button', { name: /확인|들어가기/ }).click()
      await waitForStudentHome(page)
    } else {
      await page.goto('/login')
      await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
      await expect(page.getByRole('combobox', { name: '현재 자녀 선택' })).toBeVisible()
    }
    await navigate(page, `/${role}/help`)
    await expect(page.getByText(role === 'student' ? '사고뭉치를 쓰는 방법을 알려 줄게요.' : '학습 기록을 읽는 방법과 이용 안내를 확인하세요.', { exact: true })).toBeVisible()
    await navigate(page, `/${role}/support`)
    const support = page.locator('.service-support')
    await expect(support).toContainText(role === 'student' ? '궁금한 점이나 이상한 결과를 알려 주세요.' : '일반 이용 문의와 학습 결과 오류를 구분해서 접수합니다.')
    await expect(support).toContainText(role === 'student' ? '이름, 학교, 전화번호, 사는 곳, 비밀번호는 적지 마세요.' : '비밀번호·카드 정보·실제 아동 개인정보는 적지 마세요.')
    await support.getByLabel('제목', { exact: true }).fill('합성 고객센터 검증')
    await support.getByLabel('내용', { exact: true }).fill('실제 접수 없이 오류 안내를 검증하는 합성 문의입니다.')
    await support.getByRole('button', { name: '접수하기', exact: true }).click()
    const alert = support.getByRole('alert')
    await expect(alert).toContainText('문의를 접수하지 못했습니다.')
    await expect(alert).toContainText('잠시 뒤 다시 접수해 주세요.')
    await expect(alert).not.toContainText(/SYNTHETIC_SUPPORT_FAILURE|synthetic-support-trace|확인 번호|문제 자세히 보기/)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    await support.screenshot({ path: info.outputPath(`1094-${role}-support.png`) })
  })
}
