import { test, expect } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function student(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await expect(page).toHaveURL(/\/student\/home/)
}

async function navigate(page: Page, path: string) {
  await page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)
}

async function landmarks(page: Page) {
  await expect(page.getByRole('main')).toHaveCount(1)
  const invalid = await page.locator('main,aside').evaluateAll(elements => elements.filter(el =>
    el.parentElement?.closest('main,aside,nav,[role="region"],section[aria-label],section[aria-labelledby],header,footer'),
  ).map(el => el.outerHTML.slice(0, 160)))
  expect(invalid).toEqual([])
}

async function target44(locator: Locator) {
  const box = await locator.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.width).toBeGreaterThanOrEqual(44)
  expect(box!.height).toBeGreaterThanOrEqual(44)
}

async function contrast(locator: Locator) {
  const ratio = await locator.evaluate(el => {
    const rgb = (color: string) => color.match(/[\d.]+/g)!.slice(0, 3).map(Number)
    const luminance = (color: number[]) => color.map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 })
      .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0)
    let bg: Element | null = el
    while (bg && getComputedStyle(bg).backgroundColor === 'rgba(0, 0, 0, 0)') bg = bg.parentElement
    if (!bg) throw new Error('No opaque background')
    const values = [luminance(rgb(getComputedStyle(el).color)), luminance(rgb(getComputedStyle(bg).backgroundColor))].sort((a, b) => b - a)
    return (values[0] + 0.05) / (values[1] + 0.05)
  })
  expect(ratio).toBeGreaterThanOrEqual(4.5)
}

async function work(page: Page) {
  await student(page)
  const attemptId = await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/student.ts'
    const { fixtureStore, persistFixtureState } = await import(path)
    const data = fixtureStore.snapshot(), child = data.session.child
    const sample = data.attempts.find((a: { mission: { inputType: string } }) => a.mission.inputType === 'NARRATIVE')
    if (!sample) throw new Error('Missing synthetic narrative mission')
    const mission = { ...sample.mission, grade: child.grade }
    const attempt = await fixtureStore.start(mission, child)
    persistFixtureState()
    return attempt.attemptId as string
  })
  await navigate(page, `/student/attempts/${attemptId}`)
  await expect(page.locator('.st-work h1')).toBeFocused()
}

test('#639·#640 학생 화면 본문·이름줄 대비·도움말·공책 터치 영역 @responsive', async ({ page }) => {
  await student(page)
  for (const path of ['home', 'room', 'album', 'missions', 'journal', 'settings']) {
    await navigate(page, `/student/${path}`)
    await landmarks(page)
    await contrast(page.locator('.st-sub'))
    await target44(page.locator('.st-support-menu summary'))
    if (path === 'journal') for (const filter of await page.locator('.cj-filters select').all()) await target44(filter)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  }
  await navigate(page, '/student/attempts/missing-accessibility-fixture')
  await expect(page.getByRole('alert')).toBeVisible()
  await landmarks(page)
})

test('#640 미션 안내 배지 대비·닫기 조작 영역·키보드 복귀 @responsive', async ({ page }) => {
  await student(page)
  const start = page.getByRole('button', { name: '시작하기', exact: true })
  await start.click()
  const dialog = page.getByRole('dialog')
  await contrast(dialog.locator('.cj-badge'))
  await target44(dialog.getByRole('button', { name: '창 닫기' }))
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(start).toBeFocused()
})

test('#639·#641 풀이 진입·제출 결과 포커스, 저장·실패 알림 유지 @responsive', async ({ page }) => {
  await work(page)
  await landmarks(page)
  await expect(page.getByRole('region', { name: '미션 작성기' })).toBeVisible()
  const answer = page.getByRole('textbox', { name: '내 생각과 까닭', exact: true })
  await answer.fill('저는 찬성해요. 친구와 함께 생각하면 서로 다른 까닭을 배울 수 있기 때문이에요.')
  await expect(page.locator('.ux-save-line[role=status]')).toContainText('저장했어요')
  await expect(answer).toBeFocused()
  await page.getByRole('combobox', { name: '상태 시연', exact: true }).selectOption('submit-fail')
  const submit = page.getByRole('button', { name: '다 썼어요', exact: true })
  await submit.click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(submit).toBeVisible()
  await expect(answer).toHaveValue(/서로 다른 까닭/)
  await page.getByRole('combobox', { name: '상태 시연', exact: true }).selectOption('normal')
  await submit.click()
  const result = page.locator('.ux-feedback[role=status]')
  await expect(result).toBeFocused()
  await expect(result).not.toContainText('준비하고 있어요', { timeout: 15_000 })
  await expect(result).toBeFocused()
  await page.getByRole('button', { name: '공책으로', exact: true }).focus()
  await expect(page.getByRole('button', { name: '공책으로', exact: true })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('#639·#640 학부모 본문 랜드마크·보조 메뉴·본문 건너뛰기 @responsive', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  for (const path of ['journal', 'report', 'settings', 'devices']) {
    await navigate(page, `/parent/${path}`)
    await landmarks(page)
  }
  await navigate(page, '/parent/journal')
  await expect(page.getByRole('region', { name: '학생 답변 공개 상태' })).toBeVisible()
  for (const link of await page.locator('.ws-side .ws-support a').all()) if (await link.isVisible()) await target44(link)
  const skip = page.getByRole('link', { name: '본문으로 건너뛰기' })
  await skip.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#parent-main')).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
