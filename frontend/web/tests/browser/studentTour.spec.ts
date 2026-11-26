import { skipStudentTour } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #1038 학생 화면 둘러보기(대화창). 목업 완료 기록은 sessionStorage라 시험마다 미완료에서 시작한다.
// 시연 학생(목업 기본): 공책이 비어 있고, 친구 공개가 꺼져 있다(공개 미동의) → 4·6번은 대체 대사
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function login(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await expect(page).toHaveURL(/\/student\/home/)
}
const tour = (page: Page) => page.getByRole('dialog', { name: /화면 둘러보기$/ })
/** 화면 읽기용 대사 전체(글자 효과와 무관) */
const said = (page: Page) => page.locator('#st-tour-line')
const typed = (page: Page) => tour(page).locator('.st-tour-text')
const ring = (page: Page) => page.locator('[data-tour-ring]')
function completions(page: Page) {
  const puts: string[] = []
  page.on('request', r => { if (r.method() === 'PUT' && new URL(r.url()).pathname.endsWith('/students/me/onboarding')) puts.push(r.url()) })
  return puts
}
/** n번 대사가 다 나올 때까지 기다린 뒤(앞 대사의 ▼를 보고 누르지 않게) key로 다음 */
async function next(page: Page, n: number, key = 'Enter') {
  await expect(tour(page).locator('.st-tour-count')).toHaveText(`${n} / 8`)
  await expect(tour(page).locator('.st-tour-next')).toBeVisible()
  await page.keyboard.press(key)
}

test('첫 로그인: 자동 시작 → 8개 대사를 화면을 옮기며 끝까지 → 완료 기록, 다음 홈 진입에는 안 뜬다 @responsive', async ({ page }) => {
  const puts = completions(page)
  await login(page)
  await expect(tour(page)).toBeVisible()
  await expect(page.locator('[data-tour-home]')).toHaveAttribute('data-tour-home', 'none')
  await expect(said(page)).toHaveText('1/8. 안녕! 나는 솜뭉치야. 네가 쓴 답은 학부모님도 보실 수 있어. 지금부터 화면을 하나씩 같이 둘러보자!')
  await expect(tour(page).locator('.st-tour-name')).toHaveText('솜뭉치')
  // 초점은 대화창 안, 뒤 화면은 막힘
  await expect(page.locator('.st-tour-box')).toBeFocused()
  expect(await page.locator('.st-shell').getAttribute('inert')).not.toBeNull()
  await page.keyboard.press('Tab')
  await expect(tour(page).getByRole('button', { name: '그만 볼래', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.locator('.st-tour-box')).toBeFocused()

  const steps: [RegExp, RegExp, string | null][] = [
    [/\/student\/home\?tour=1$/, /안녕!/, null],
    [/\/student\/home\?tour=2$/, /(오늘 문제|이어서 풀기)/, 'any'],
    [/\/student\/home\?tour=3$/, /(월요일부터 금요일까지)/, 'home-days'],
    [/\/student\/journal\?tour=4$/, /아직 비어 있지만/, null],
    [/\/student\/activities\?tour=5$/, /생각 놀이/, 'activities-list'],
    [/\/student\/community\?tour=6$/, /내 답이 친구들에게 안 보여/, null],
    [/\/student\/room\?tour=7$/, /방을 꾸밀 수 있어/, 'room-decor'],
    [/\/student\/home\?tour=8$/, /도움말에서 언제든/, null],
  ]
  for (const [i, [url, line, target]] of steps.entries()) {
    await expect(page).toHaveURL(url)
    await expect(said(page)).toHaveText(new RegExp(`^${i + 1}/8\\. .*${line.source}`))
    await expect(tour(page).locator('.st-tour-count')).toHaveText(`${i + 1} / 8`)
    if (target === 'any') {
      // 홈 상태(실제 날짜)에 따라 오늘 문제 버튼 강조 또는 대체 대사
    } else if (target) await expect(ring(page)).toHaveAttribute('data-tour-ring', target)
    else await expect(ring(page)).toHaveCount(0)
    // 강조한 곳이 대화창에 가리지 않는다(좁은 화면은 스크롤, 한 화면에 맞춘 넓은 화면은 대화창을 위로)
    if (target && target !== 'any') {
      await expect(async () => {
        const dock = (await page.locator('.st-tour-dock').boundingBox())!
        const spot = (await page.locator(`[data-tour="${target}"]`).boundingBox())!
        const overlap = Math.min(spot.y + spot.height, dock.y + dock.height) - Math.max(spot.y, dock.y)
        expect(overlap, target).toBeLessThanOrEqual(0)
      }).toPass({ timeout: 3_000 })
    }
    await next(page, i + 1)
  }
  await expect(tour(page)).toBeHidden()
  await expect(page).toHaveURL(/\/student\/home$/)
  await expect.poll(() => puts.length).toBe(1)
  expect(await page.locator('.st-shell').getAttribute('inert')).toBeNull()

  await page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '내 공책', exact: true }).click()
  await page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '홈', exact: true }).click()
  await expect(page.locator('[data-tour-home]')).toHaveAttribute('data-tour-home', 'none')
  await expect(tour(page)).toHaveCount(0)
  expect(puts).toHaveLength(1)
})

test('넘기기: 글자가 다 나오기 전에 누르면 한 번에 다 나오고, 한 번 더 누르면 다음 대사', async ({ page }) => {
  await login(page)
  await expect(tour(page)).toBeVisible()
  await page.locator('.st-tour-box').click()
  await expect(typed(page)).toHaveText('안녕! 나는 솜뭉치야. 네가 쓴 답은 학부모님도 보실 수 있어. 지금부터 화면을 하나씩 같이 둘러보자!')
  await expect(page).toHaveURL(/tour=1$/)
  await page.locator('.st-tour-box').click()
  await expect(page).toHaveURL(/tour=2$/)
  // Space도 같다
  await next(page, 2, ' ')
  await expect(page).toHaveURL(/tour=3$/)
})

test('그만 볼래와 Esc는 완료를 기록하고 홈으로 닫는다', async ({ page }) => {
  const puts = completions(page)
  await login(page)
  await expect(tour(page)).toBeVisible()
  await next(page, 1)
  await next(page, 2)
  await next(page, 3)
  await expect(page).toHaveURL(/\/student\/journal\?tour=4$/)
  await page.keyboard.press('Escape')
  await expect(tour(page)).toBeHidden()
  await expect(page).toHaveURL(/\/student\/home$/)
  await expect.poll(() => puts.length).toBe(1)
})

test('끝내지 않고 나가면(새로 고침 뒤 홈으로 다시 들어오면) 1번부터 다시', async ({ page }) => {
  const puts = completions(page)
  await login(page)
  await next(page, 1)
  await expect(page).toHaveURL(/tour=2$/)
  await page.goto('/student/home')
  await expect(tour(page)).toBeVisible()
  await expect(page).toHaveURL(/\/student\/home\?tour=1$/)
  await expect(said(page)).toContainText('1/8. 안녕!')
  expect(puts).toHaveLength(0)
})

test('도움말 "화면 둘러보기 다시 하기": 서버 기록은 그대로 두고 1번부터, 테마 없는 주는 홈 대사를 상태에 맞춘다 @responsive', async ({ page }) => {
  const puts = completions(page)
  await login(page)
  await skipStudentTour(page)
  await expect.poll(() => puts.length).toBe(1)
  // 테마가 아직 안 열린 주
  const applied = page.evaluate(() => new Promise<void>(resolve =>
    addEventListener('sagomungchi:mock-theme-state-applied', () => setTimeout(resolve, 50), { once: true })))
  await page.getByRole('combobox', { name: '목업 홈 상태' }).selectOption('none')
  await applied
  await expect(page.getByRole('heading', { name: '이번 주 테마를 준비하고 있어요' })).toBeVisible()

  await page.locator('.st-support-menu summary').click()
  await page.getByRole('link', { name: '이용 도움말', exact: true }).click()
  const again = page.getByRole('link', { name: '화면 둘러보기 다시 하기', exact: true })
  expect((await again.boundingBox())!.y).toBeLessThan((await page.getByRole('heading', { name: '이용 도움말', exact: true }).boundingBox())!.y)
  await again.click()
  await expect(tour(page)).toBeVisible()
  await expect(said(page)).toContainText('1/8. 안녕!')
  await next(page, 1)
  await expect(said(page)).toHaveText(/^2\/8\. 이번 주 테마를 준비하고 있어/)
  await expect(ring(page)).toHaveCount(0)
  await next(page, 2)
  await expect(said(page)).toHaveText(/^3\/8\. 테마가 열리면/)
  await expect(ring(page)).toHaveCount(0)
  await tour(page).getByRole('button', { name: '그만 볼래', exact: true }).click()
  await expect(tour(page)).toBeHidden()
  // 이미 기록이 있으니 다시 하기를 닫아도 기록 요청을 더 보내지 않는다
  await page.waitForTimeout(300)
  expect(puts).toHaveLength(1)
})

test('움직임 줄이기: 글자 효과 없이 대사가 한 번에 나온다', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await login(page)
  await expect(tour(page)).toBeVisible()
  await expect(typed(page)).toHaveText('안녕! 나는 솜뭉치야. 네가 쓴 답은 학부모님도 보실 수 있어. 지금부터 화면을 하나씩 같이 둘러보자!', { timeout: 300 })
  await expect(tour(page).locator('.st-tour-next')).toBeVisible()
})

test('새로 고침 뒤 주소로 이어 본 둘러보기를 끝내면 다시 1번부터 뜨지 않는다(끝낸 직후 기록 응답 전에도)', async ({ page }) => {
  const puts = completions(page)
  await login(page)
  await next(page, 1)
  await expect(page).toHaveURL(/tour=2$/)
  // 새로 고침하면 이 탭의 자동 시작 기록이 비고, 주소(?tour=N)로 이어 본다
  await page.goto('/student/home?tour=8')
  await expect(said(page)).toContainText('8/8.')
  await next(page, 8)
  await expect(page).toHaveURL(/\/student\/home$/)
  await page.waitForTimeout(2_000)
  await expect(tour(page)).toHaveCount(0)
  await expect(page).toHaveURL(/\/student\/home$/)
  expect(puts.length).toBeGreaterThanOrEqual(1)
})
