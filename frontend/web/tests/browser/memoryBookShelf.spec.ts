import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// #1000 학부모 추억 그림책 책장(MSW 목업, core #999 계약 lockedCount·canCreate). 가상 자녀만.

async function login(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/parent\/journal/)
}
const noOverflow = async (page: Page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0)
/**
 * 문서마다 `/memory-books/rounds` 응답을 바꾼다. MSW 서비스 워커가 답하는 요청은 page.route로 못 잡아 페이지 fetch를 감싼다.
 * `times`번만 바꾸고 그 뒤는 목업 그대로(0이면 계속 바꿈). 개발 StrictMode가 첫 조회를 바로 취소하고 다시 부르므로
 * 한 틱 뒤 취소된 요청은 세지 않는다(화면이 실제로 받은 응답만 센다)
 */
async function stubRounds(page: Page, stub: { status: number; body: unknown; times?: number }) {
  await page.addInitScript(({ status, body, times }) => {
    const original = window.fetch.bind(window)
    let used = 0
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (!/\/memory-books\/rounds(\?|$)/.test(url)) return original(input, init)
      return new Promise<Response>((resolve, reject) => setTimeout(() => {
        if (init?.signal?.aborted) return reject(new DOMException('취소된 요청', 'AbortError'))
        if (times !== 0 && used >= times) return resolve(original(input, init))
        used += 1
        const type = status >= 400 ? 'application/problem+json' : 'application/json'
        resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } }))
      }, 0))
    }
  }, { status: stub.status, body: stub.body, times: stub.times ?? 0 })
}

test('유료 자녀: 표지 책장에서 회차마다 그림책 발급, 잠금 안내 없음 @responsive', async ({ page }) => {
  await login(page)
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

test('유료 자녀: 발급 → 받기 옆 "같이 읽었어요" → 누르면 단추 대신 표지에 같이 읽음 날짜(#1026) @responsive', async ({ page }) => {
  // 같이 읽음 뒤 회차 목록 다시 받기를 1.5초 늦춰, 다시 받을 때까지 단추가 잠겨 있는지 본다(목업은 너무 빨라 그냥은 못 봄)
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    let marked = false
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (/\/read-together$/.test(url)) marked = true
      if (marked && /\/memory-books\/rounds(\?|$)/.test(url)) return new Promise<void>((r) => setTimeout(r, 1500)).then(() => original(input, init))
      return original(input, init)
    }
  })
  await login(page)
  await page.goto('/parent/report?childId=demo-seoyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  const row = books.getByRole('list', { name: '그림책을 발급할 수 있는 회차' }).getByRole('listitem').first()
  await row.getByRole('button', { name: '그림책 발급' }).click()
  // 목업은 4초 뒤 완성, 화면은 3초마다 다시 본다
  await expect(row.getByRole('button', { name: '받기' })).toBeVisible({ timeout: 15_000 })
  const read = row.getByRole('button', { name: '같이 읽었어요' })
  await expect(read).toBeVisible()
  await expect(row.locator('.memory-shelf-read')).toHaveCount(0)
  // 받기·같이 읽었어요 두 단추가 좁은 화면에서도 넘치지 않는다
  await noOverflow(page)
  await read.click()
  // 누른 직후: 회차 목록을 다시 받을 때까지 단추가 잠겨 있다(다시 눌리는 틈 없음).
  // PUT은 바로 끝나므로, 0.8초 뒤(목록은 아직 늦춰지는 중)에도 잠겨 있어야 onSuccess가 다시 받기를 기다린 것이다
  await expect(read).toBeDisabled()
  await page.waitForTimeout(800)
  await expect(read).toBeDisabled()
  const kst = new Date(Date.now() + 9 * 3600_000)
  const label = `같이 읽음 ${String(kst.getUTCMonth() + 1).padStart(2, '0')}/${String(kst.getUTCDate()).padStart(2, '0')}`
  await expect(row.getByText(label, { exact: true })).toBeVisible()
  await expect(read).toHaveCount(0)
  await expect(row.getByRole('button', { name: '받기' })).toBeVisible()
  await noOverflow(page)
})

test('무료 자녀: 최근 4주 표지만, 발급 대신 잠금, 숨긴 회차 수 안내 → 비교표로 @responsive', async ({ page }) => {
  await login(page)
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
  await page.goto('/parent/report?childId=demo-doyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  await expect(books.getByRole('list', { name: '최근 4주 그림책 표지' }).getByRole('listitem')).toHaveCount(3)
  await expect(books.getByText(/잠긴 책/)).toHaveCount(0)
  await expect(books.getByRole('note')).toContainText('그림책 만들기와 지난 그림책 모아 보기는 프리미엄에서 할 수 있어요.')
})

test('#1064: 학생 공개 설정 없이도 책장이 보이고 비공개 안내가 없다', async ({ page }) => {
  await login(page)
  await page.goto('/parent/report?childId=demo-doyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  await expect(books.getByRole('list').first()).toBeVisible()
  await expect(books.getByText(/답 보여 주기/)).toHaveCount(0)
})

test('회차 목록을 못 불러오면 다시 불러오기로 책장을 다시 받는다 @responsive', async ({ page }) => {
  await stubRounds(page, { status: 500, body: { status: 500, code: 'INTERNAL_ERROR', title: '잠시 후 다시 시도해 주세요.', retryable: true }, times: 1 })
  await login(page)
  await page.goto('/parent/report?childId=demo-seoyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  const alert = books.getByRole('alert')
  await expect(alert).toContainText('회차 목록을 불러오지 못했습니다.')
  const retry = alert.getByRole('button', { name: '다시 불러오기' })
  expect((await retry.boundingBox())?.height).toBeGreaterThanOrEqual(44)
  await noOverflow(page)
  await retry.click()
  await expect(books.getByRole('list', { name: '그림책을 발급할 수 있는 회차' }).locator('img.memory-shelf-cover')).toHaveCount(3)
  await expect(books.getByRole('alert')).toHaveCount(0)
})

test('무료 자녀: 최근 4주 회차가 없으면 표지 없이 잠긴 책 칸과 안내만 @responsive', async ({ page }) => {
  await stubRounds(page, { status: 200, body: { items: [], page: 0, size: 50, totalElements: 0, lockedCount: 3, canCreate: false } })
  await login(page)
  await page.goto('/parent/report?childId=demo-doyun')
  const books = page.getByRole('region', { name: '추억 그림책', exact: true })
  await expect(books.getByText('아이가 한 주 테마를 모두 마쳐 받은 기념 액자가 책장에 꽂혀요. 최근 4주에는 새로 받은 액자가 없어요.', { exact: true })).toBeVisible()
  const shelf = books.getByRole('list', { name: '최근 4주 그림책 표지' })
  await expect(shelf.locator('img.memory-shelf-cover')).toHaveCount(0)
  await expect(shelf.getByText('잠긴 책 3권', { exact: true })).toBeVisible()
  const note = books.getByRole('note')
  await expect(note).toContainText('지난 그림책 3권은 프리미엄에서 볼 수 있어요.')
  await expect(note.getByRole('link', { name: '무료와 프리미엄 비교 보기' })).toHaveAttribute('href', '/parent/billing?childId=demo-doyun#plan-compare')
  await noOverflow(page)
})
