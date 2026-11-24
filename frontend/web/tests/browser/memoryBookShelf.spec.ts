import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// #1000 학부모 추억 그림책 책장(MSW 목업, core #999 계약 lockedCount·canCreate). 가상 자녀만.

async function login(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/parent\/journal/)
}
async function share(page: Page, childId: string) {
  await page.evaluate(async id => { const path = '/src/mocks/fixtures/sharing.ts'; const { saveSharing } = await import(path); saveSharing(id, true) }, childId)
}
const noOverflow = async (page: Page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0)

test('유료 자녀: 표지 책장에서 회차마다 그림책 발급, 잠금 안내 없음 @responsive', async ({ page }) => {
  await login(page)
  await share(page, 'demo-seoyun')
  await page.goto('/parent/report?childId=demo-seoyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  const shelf = books.getByRole('list', { name: '그림책을 발급할 수 있는 회차' })
  await expect(shelf.getByRole('listitem')).toHaveCount(3)
  await expect(shelf.locator('img.memory-shelf-cover')).toHaveCount(3)
  await expect(shelf.getByRole('button', { name: '그림책 발급' })).toHaveCount(3)
  await expect(books.getByRole('note')).toHaveCount(0)
  await expect(books.getByText(/잠긴 책/)).toHaveCount(0)
  await noOverflow(page)
})

test('무료 자녀: 최근 4주 표지만, 발급 대신 잠금, 숨긴 회차 수 안내 → 비교표로 @responsive', async ({ page }) => {
  await login(page)
  await share(page, 'demo-doyun')
  await page.evaluate(() => sessionStorage.setItem('sagomungchi:msw-memory-book-locked', '2'))
  await page.goto('/parent/report?childId=demo-doyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  const shelf = books.getByRole('list', { name: '최근 4주 그림책 표지' })
  await expect(shelf.locator('img.memory-shelf-cover')).toHaveCount(3)
  await expect(shelf.getByRole('button', { name: '그림책 발급' })).toHaveCount(0)
  await expect(shelf.getByText('발급은 프리미엄')).toHaveCount(3)
  await expect(shelf.getByText('잠긴 책 2권', { exact: true })).toBeVisible()
  const note = books.getByRole('note')
  await expect(note).toContainText('지난 그림책 2권은 프리미엄에서 볼 수 있어요.')
  await noOverflow(page)
  await note.getByRole('link', { name: '무료와 프리미엄 비교 보기' }).click()
  await expect(page).toHaveURL(/\/parent\/billing\?childId=demo-doyun#plan-compare$/)
})

test('무료 자녀: 숨긴 회차가 없으면 잠긴 책 칸 없이 프리미엄 안내만', async ({ page }) => {
  await login(page)
  await share(page, 'demo-doyun')
  await page.goto('/parent/report?childId=demo-doyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  await expect(books.getByRole('list', { name: '최근 4주 그림책 표지' }).getByRole('listitem')).toHaveCount(3)
  await expect(books.getByText(/잠긴 책/)).toHaveCount(0)
  await expect(books.getByRole('note')).toContainText('그림책 만들기와 지난 그림책 모아 보기는 프리미엄에서 할 수 있어요.')
})

test('원문 비공개 자녀는 책장 대신 기존 안내', async ({ page }) => {
  await login(page)
  await page.goto('/parent/report?childId=demo-doyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  await expect(books.getByRole('alert')).toContainText('답 보여 주기를 켜야')
  await expect(books.getByRole('list')).toHaveCount(0)
})
