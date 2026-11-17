import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill('content@example.test')
  await page.getByLabel('비밀번호', { exact: true }).fill('demo-only')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await page.getByRole('link', { name: '꾸미기 아이템', exact: true }).click()
})

for (const [slot, label, asset] of [
  ['FLOOR', '바닥', 'room/floor-grass.png'],
  ['DECOR', '방 소품', 'room/decor-plant.png'],
  ['HAT', '모자', 'looks/hat-acorn.svg'],
]) test(`${label} 등록·수정·판매 중단과 칸 필터 (#706)`, async ({ page }, testInfo) => {
  const name = `${label} 브라우저 시험`
  await page.getByRole('button', { name: '새 아이템', exact: true }).click()
  await page.getByLabel('아이템 코드', { exact: true }).fill(`${slot}_BROWSER_TEST`)
  await page.getByLabel('아이템 칸', { exact: true }).selectOption(slot)
  await page.getByLabel('아이템 이름', { exact: true }).fill(name)
  await page.getByLabel('필요 포인트', { exact: true }).fill('30')
  await page.getByLabel('그림 키', { exact: true }).fill(asset)
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await page.getByLabel('아이템 칸 필터', { exact: true }).selectOption(slot)
  const row = page.locator('.ad-table tbody tr').filter({ hasText: `${slot}_BROWSER_TEST` })
  await expect(row).toBeVisible()
  await expect(row.locator('td').nth(1)).toHaveText(label)
  await row.getByRole('button', { name: `${name} 아이템 수정`, exact: true }).click()
  await expect(page.getByLabel('아이템 코드', { exact: true })).toBeDisabled()
  await expect(page.getByLabel('아이템 칸', { exact: true })).toBeDisabled()
  await page.getByLabel('아이템 이름', { exact: true }).fill(name + ' 수정')
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(row).toContainText(name + ' 수정')
  await page.getByRole('button', { name: '판매 중단', exact: true }).click()
  await expect(row.getByText('판매 중단', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`${slot.toLowerCase()}-admin.png`), fullPage: true })
})

test('칸 필터를 바꾸면 첫 페이지로 돌아온다 (#706)', async ({ page }) => {
  await page.getByRole('button', { name: '다음 아이템', exact: true }).click()
  await expect(page.getByText('2페이지', { exact: true })).toBeVisible()
  await page.getByLabel('아이템 칸 필터', { exact: true }).selectOption('FLOOR')
  await expect(page.locator('.ad-table tbody tr').filter({ hasText: 'FLOOR_PREVIEW' })).toBeVisible()
  await page.getByLabel('아이템 칸 필터', { exact: true }).selectOption('')
  await expect(page.getByText('1페이지', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '이전 아이템', exact: true })).toBeDisabled()
})
