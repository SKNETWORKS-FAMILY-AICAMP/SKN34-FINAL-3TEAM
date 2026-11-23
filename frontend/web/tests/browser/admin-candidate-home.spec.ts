import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function signIn(page: Page, email: string) {
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill(email)
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
}

test('운영 대기 카드가 권한별 건수와 같은 조건의 목록을 연다', async ({ page }) => {
  const response = page.waitForResponse(r => r.url().includes('/admin/overview/workload?') && r.status() === 200)
  await signIn(page, 'ops@example.test')
  const counts = await (await response).json()
  const area = page.getByRole('region', { name: '운영 대기 현황' })
  const inquiries = area.getByRole('link', { name: /답변 대기 문의/ })
  await expect(inquiries).toContainText(counts.pendingInquiries + '건')
  await expect(area.getByRole('link', { name: /신규 오류 신고/ })).toContainText(counts.receivedReports + '건')
  await expect(area.getByRole('link', { name: /재처리할 실패 작업/ })).toContainText(counts.failedJobs + '건')
  await expect(area.getByRole('link', { name: /환불 승인 대기/ })).toHaveCount(0)
  await expect(page.getByRole('region', { name: '테마 검수·게시', exact: true })).toHaveCount(0)
  await inquiries.click()
  await expect(page.getByLabel('문의 상태', { exact: true })).toHaveValue('RECEIVED')
  await page.goBack()
  await area.getByRole('link', { name: /재처리할 실패 작업/ }).click()
  await expect(page.getByLabel('작업 상태', { exact: true })).toHaveValue('FAILED')
  expect(new URL(page.url()).searchParams.get('from')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
})

test('콘텐츠 관리자가 홈에서 비교 대기와 추가 생성 요청으로 이동한다', async ({ page }) => {
  await signIn(page, 'content@example.test')
  const queue = page.getByRole('region', { name: '테마 검수·게시', exact: true })
  await expect(page.getByRole('region', { name: '운영 대기 현황' })).toHaveCount(0)
  const review = queue.getByRole('link', { name: '테마 검수 열기', exact: true })
  await expect(review).toHaveCSS('color', 'rgb(22, 56, 70)')
  await expect(review).toHaveCSS('background-color', 'rgb(255, 255, 255)')
  await review.click()
  await expect(page).toHaveURL(/\/admin\/theme-drafts\?draftId=.+/)
  await page.goBack()
  const compare = queue.getByRole('link', { name: /재생성 장면 비교 대기/ })
  await expect(compare).toContainText(/\d+건/)
  await compare.click()
  await expect(page).toHaveURL(/comparisonPending=true/)
  await page.goBack()
  await queue.getByRole('link', { name: '테마 추가 생성 요청' }).click()
  await expect(page.getByLabel('테마 주제 키워드')).toBeVisible()
})

test('결제 조회 관리자는 환불 대기 목록만 열 수 있다', async ({ page }) => {
  await signIn(page, 'payment@example.test')
  const area = page.getByRole('region', { name: '운영 대기 현황' })
  await expect(area.getByRole('link')).toHaveCount(1)
  await area.getByRole('link', { name: /환불 승인 대기/ }).click()
  await expect(page.getByLabel('환불 상태 필터')).toHaveValue('REQUESTED')
})
