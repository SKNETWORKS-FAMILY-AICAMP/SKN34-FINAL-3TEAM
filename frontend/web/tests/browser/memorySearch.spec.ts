import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #567 추억 앨범 "기억으로 찾기": 예시 칩은 채우기만, 결과 카드 → 회차 상세, 설명 근거 연결, 설명 실패에도 결과 유지, 찾기 장애 재시도
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function album(page: Page, scenario?: string) {
  await page.goto('/student/login')
  if (scenario) await page.evaluate(s => sessionStorage.setItem('sagomungchi:msw-memory', s), scenario)
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
  await page.evaluate(() => { history.pushState({}, '', '/student/album'); dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page.getByRole('heading', { name: '기억으로 찾기', exact: true })).toBeVisible()
}
const box = (page: Page) => page.getByRole('searchbox', { name: '찾고 싶은 기억' })

test('예시 칩은 검색창만 채우고 찾기를 누르면 카드·근거 번호가 나온다 @responsive', async ({ page }) => {
  let searched = 0
  page.on('request', r => { if (r.url().includes('/memories/search')) searched++ })
  await album(page)
  await expect(page.getByText('예시', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '예시 질문 넣기: 고양이가 나오는 글' }).click()
  await expect(box(page)).toHaveValue('고양이가 나오는 글')
  await expect(box(page)).toBeFocused()
  expect(searched, '칩은 하루 횟수를 쓰지 않음').toBe(0)

  await page.getByRole('button', { name: '찾기', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await box(page).fill('생각')
  await page.getByRole('button', { name: '찾기', exact: true }).click()
  const found = page.getByRole('list', { name: '찾은 주' })
  await expect(found).toBeVisible()
  await expect(page.getByText(/「생각」와 가까운 주 \d개/)).toBeVisible()
  await expect(found.getByLabel('근거 1')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)

  await found.getByRole('button', { name: '그때 기록 보기 →' }).first().click()
  await expect(page).toHaveURL(/\/student\/album\/[^/]+\/\d{4}-\d{2}-\d{2}$/)
})

test('빈 질문은 보내지 않고 안내한다', async ({ page }) => {
  let searched = 0
  page.on('request', r => { if (r.url().includes('/memories/search')) searched++ })
  await album(page)
  await box(page).fill('   ')
  await page.getByRole('button', { name: '찾기', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('찾고 싶은 기억을 한 글자 이상 써 주세요.')
  expect(searched).toBe(0)
})

test('설명은 문장마다 근거 번호로 카드에 이어지고 한 번만 부른다', async ({ page }) => {
  await album(page)
  await box(page).fill('생각')
  await page.getByRole('button', { name: '찾기', exact: true }).click()
  await page.getByRole('button', { name: '뭉치에게 설명 듣기' }).click()
  const cite = page.getByRole('button', { name: /^근거 1: / })
  await expect(cite).toBeVisible()
  await expect(page.getByRole('button', { name: '뭉치에게 설명 듣기' })).toBeDisabled()
  await cite.click()
  await expect(page.getByRole('list', { name: '찾은 주' }).locator('> li').first()).toBeFocused()
})

test('설명이 실패해도 찾은 카드는 그대로 남는다(대체 문장 없음)', async ({ page }) => {
  await album(page, 'EXPLAIN_FAILED')
  await box(page).fill('생각')
  await page.getByRole('button', { name: '찾기', exact: true }).click()
  await page.getByRole('button', { name: '뭉치에게 설명 듣기' }).click()
  await expect(page.getByText('지금은 설명을 만들지 못했어요. 찾은 기록은 그대로 볼 수 있어요.')).toBeVisible()
  await expect(page.getByRole('list', { name: '찾은 주' })).toBeVisible()
  await expect(page.getByRole('button', { name: /^근거 \d: / })).toHaveCount(0)
})

test('찾기 장애(503)는 다시 찾기로 다시 부른다', async ({ page }) => {
  await album(page, 'SEARCH_DOWN')
  await box(page).fill('생각')
  await page.getByRole('button', { name: '찾기', exact: true }).click()
  await expect(page.getByText(/지금은 찾기가 잠시 쉬고 있어요/)).toBeVisible()
  await page.evaluate(() => sessionStorage.removeItem('sagomungchi:msw-memory'))
  await page.getByRole('button', { name: '다시 찾기' }).click()
  await expect(page.getByRole('list', { name: '찾은 주' })).toBeVisible()
})
