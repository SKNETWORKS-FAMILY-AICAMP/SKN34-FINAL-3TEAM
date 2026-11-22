import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// #728 표현 검토 라벨링 화면 (FN-ADM-24): 글만 보이고, 라벨 전/완료, 빈 목록·실패·권한 없음 구분
async function open(page: Page, email = 'ops@example.test') {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill(email)
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await page.goto('/admin/expressions')
}
async function scenario(page: Page, value: string) {
  await page.locator('.ad-demo-tools > summary').click()
  await page.getByRole('combobox', { name: '상태 시연', exact: true }).selectOption(value)
  await page.locator('.ad-demo-tools > summary').click()
}

test('라벨 전 글을 읽고 라벨을 붙이면 라벨 완료로 옮겨 간다 @responsive', async ({ page }) => {
  await open(page)
  await expect(page.getByRole('heading', { name: '표현 검토 라벨링', exact: true })).toBeVisible()
  const list = page.getByRole('region', { name: '표현 검토' })
  await expect(list.getByRole('article')).toHaveCount(2)
  await expect(list.getByRole('article').first()).toContainText('친구가 너무 답답하게 굴어서') // 오래된 순
  await expect(list.locator('.expression-review-text').nth(1)).toHaveText('개발용 합성 공유물\n두 번째 줄') // 줄바꿈 그대로
  await expect(list.getByText(/학생|ID/)).toHaveCount(1) // 안내 문장의 "학생 이름·ID는 없습니다"만
  const first = list.getByRole('article').first()
  await first.getByRole('button', { name: '막을 글', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '"막을 글"(으)로 저장했습니다.' })).toBeVisible()
  await expect(list.getByRole('article')).toHaveCount(1)
  await page.getByRole('button', { name: '라벨 완료', exact: true }).click()
  const labeled = list.getByRole('article')
  await expect(labeled).toHaveCount(2)
  await expect(labeled.first()).toContainText('친구가 너무 답답하게 굴어서') // 최근 라벨 순
  await expect(labeled.first().getByRole('button', { name: '막을 글', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await labeled.first().getByRole('button', { name: '건너뜀', exact: true }).click()
  await expect(labeled.first().getByRole('button', { name: '건너뜀', exact: true })).toHaveAttribute('aria-pressed', 'true')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('출처 필터는 신고 숨김 공유물만 보여 준다', async ({ page }) => {
  await open(page)
  await page.getByRole('combobox', { name: '출처', exact: true }).selectOption('COMMUNITY_REPORT')
  const list = page.getByRole('region', { name: '표현 검토' })
  await expect(list.getByRole('article')).toHaveCount(1)
  await expect(list.getByRole('article')).toContainText('신고 숨김 공유물')
})

test('빈 목록·조회 실패·권한 없음을 구분한다', async ({ page }) => {
  await open(page)
  await scenario(page, 'empty')
  await expect(page.getByText('검토할 글이 없습니다.', { exact: true })).toBeVisible()
  await scenario(page, 'query-fail')
  await expect(page.getByRole('alert')).toContainText('관리자 조회에 실패했습니다.')
  await expect(page.getByText('검토할 글이 없습니다.', { exact: true })).toHaveCount(0)
  await scenario(page, 'forbidden')
  await expect(page.getByRole('alert')).toContainText('권한')
  await expect(page.getByRole('region', { name: '표현 검토' }).getByRole('article')).toHaveCount(0)
})

test('서비스 운영 권한이 없으면 메뉴에 없고 주소로 들어가도 막힌다', async ({ page }) => {
  await open(page, 'content@example.test')
  await expect(page.getByText('FORBIDDEN · 필요한 관리자 권한이 없습니다.')).toBeVisible()
  await expect(page.getByRole('navigation', { name: '관리자 메뉴' }).getByRole('link', { name: '표현 검토', exact: true })).toHaveCount(0)
  await expect(page.getByRole('region', { name: '표현 검토' })).toHaveCount(0)
})
