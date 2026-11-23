import { waitForStudentHome } from './studentFixture.ts'
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
  await waitForStudentHome(page)
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
  const { ratio, text } = await locator.evaluate(el => {
    const rgb = (color: string) => color.match(/[\d.]+/g)!.slice(0, 3).map(Number)
    const luminance = (color: number[]) => color.map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 })
      .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0)
    let bg: Element | null = el
    while (bg && getComputedStyle(bg).backgroundColor === 'rgba(0, 0, 0, 0)') bg = bg.parentElement
    if (!bg) throw new Error('No opaque background')
    const values = [luminance(rgb(getComputedStyle(el).color)), luminance(rgb(getComputedStyle(bg).backgroundColor))].sort((a, b) => b - a)
    return { ratio: (values[0] + 0.05) / (values[1] + 0.05), text: el.textContent }
  })
  expect(ratio, `글자 대비: ${text}`).toBeGreaterThanOrEqual(4.5)
}

async function adminLogin(page: Page) {
  await page.getByLabel('로그인 ID', { exact: true }).fill('admin@example.test')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
}

test('#914 관리자 로그인·15개 메뉴의 보조 글 대비 @responsive', async ({ page }, testInfo) => {
  test.setTimeout(45_000)
  await page.goto('/admin/login')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  for (const copy of await page.locator([
    '.admin-login-eyebrow', '.admin-login-intro > p', '.admin-login-features small',
    '.admin-login-security', '.admin-login-heading > p', '.admin-login-page footer a',
  ].map(selector => `${selector}:visible`).join(', ')).all()) {
    await contrast(copy)
  }
  if (testInfo.project.name !== 'tablet') {
    await page.screenshot({ path: testInfo.outputPath('admin-login.png') })
  }
  await adminLogin(page)

  const menus = [
    'home', 'audit', 'missions', 'mission-drafts', 'themes', 'theme-drafts', 'looks',
    'support', 'errors', 'jobs', 'queues', 'models', 'expressions', 'usage', 'payments',
  ]
  const secondaryText = [
    '.ad-overview-intro > span', '.ad-mission-publication h3', '.ad-resource-list p', '.ad-time-cell',
    '.ad-empty > p', '.ad-list-footer > span', '.ad-review-guide > summary', '.ad-view-tabs button',
    '.ad-data-toolbar p', '.ad-table td small', '.ad-record-id', '.ad-note', '.ad-badge',
  ]
  for (const menu of menus) {
    await test.step(menu, async () => {
      await navigate(page, `/admin/${menu}`)
      await expect(page.getByRole('main')).toHaveAttribute('data-page', menu)
      await expect(page.getByText('불러오고 있습니다.', { exact: true }).first()).toBeHidden()
      await contrast(page.locator('.ad-page-title p'))
      const location = page.locator('.ad-location > span:visible')
      if (await location.count()) await contrast(location.first())
      await expect(page.getByText('접근 권한 확인', { exact: true })).toHaveCount(0)
      for (const selector of secondaryText) {
        const copy = page.locator(`.ad-page-content ${selector}:visible`)
        if (await copy.count()) await contrast(copy.first())
      }
      if (menu === 'home' && testInfo.project.name !== 'tablet') {
        await page.screenshot({ path: testInfo.outputPath('admin-home.png') })
      }
    })
  }

  await navigate(page, '/admin/theme-drafts?request=1')
  await page.getByLabel('테마 주제 키워드').fill('검사 실패 시연')
  await page.getByRole('button', { name: '테마 초안 생성 요청', exact: true }).click()
  const failure = page.locator('.ad-note').filter({ has: page.getByRole('heading', { name: '검사 실패', exact: true }) })
  await expect(failure).toBeVisible({ timeout: 12_000 })
  await contrast(failure.getByRole('heading'))
  await contrast(failure.locator('p').first())
})

test('#914 모바일 관리자 표는 Tab과 방향키로 스크롤할 수 있다 @responsive', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'compact', '가로 스크롤이 생기는 모바일 뷰포트에서 확인')
  await page.goto('/admin/login')
  await adminLogin(page)

  const tables = [
    ['audit', '감사 이력 표'],
    ['mission-drafts', '미션 초안 표'],
    ['usage', 'AI 사용량 표'],
    ['payments', '환불 요청 표'],
    ['payments?tab=payments', '결제 승인 내역 표'],
    ['payments?tab=reconciliation', '결제 대조 결과 표'],
  ]
  for (const [path, label] of tables) {
    await test.step(label, async () => {
      await navigate(page, `/admin/${path}`)
      const region = page.getByRole('region', { name: label, exact: true })
      await expect(region).toBeVisible()
      await expect(region).toHaveAttribute('tabindex', '0')
      await expect.poll(() => region.evaluate(el => el.scrollWidth - el.clientWidth)).toBeGreaterThan(0)
      await region.focus()
      await page.keyboard.press('Shift+Tab')
      await expect(region).not.toBeFocused()
      await page.keyboard.press('Tab')
      await expect(region).toBeFocused()
      await expect(region).toHaveCSS('outline-style', 'solid')
      await page.keyboard.press('ArrowRight')
      await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
      await expect(region).toBeFocused()
    })
  }
})

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
  // #648 새 홈에는 오늘의 미션 카드가 없어, 미션 안내 창은 "더 풀어 보기"(미션 고르기)의 미션 열기로 연다
  await page.getByRole('button', { name: /더 풀어 보기/ }).click()
  const start = page.getByRole('button', { name: '미션 열기', exact: true }).first()
  await start.click()
  // #648: 학생 미션 안내는 창이 아니라 학생 틀 안 전체 화면(시안 MissionGuide). 꼬리표 대비·돌아가기 조작 영역·Esc 뒤 초점 복귀는 그대로 본다
  const guide = page.locator('.mg-page')
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
  await contrast(guide.locator('.mg-tag'))
  await target44(guide.getByRole('button', { name: '← 미션 고르기' }))
  await page.keyboard.press('Escape')
  await expect(guide).toHaveCount(0)
  await expect(start).toBeFocused()
})

test('#639·#641 풀이 진입·제출 결과 포커스, 저장·실패 알림 유지 @responsive', async ({ page }) => {
  await work(page)
  await landmarks(page)
  await expect(page.getByRole('region', { name: '미션 작성기' })).toBeVisible()
  const answer = page.getByRole('textbox', { name: '내 생각과 이유', exact: true })
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
  await expect(page).toHaveURL(/childId=/)
  const scope = new URL(page.url()).search
  for (const path of ['journal', 'report', 'settings', 'devices']) {
    await navigate(page, `/parent/${path}${scope}`)
    await landmarks(page)
  }
  await navigate(page, `/parent/journal${scope}`)
  await expect(page.getByRole('region', { name: '학생 답변 공개 상태' })).toBeVisible()
  for (const link of await page.locator('.ws-side .ws-support a').all()) if (await link.isVisible()) await target44(link)
  const skip = page.getByRole('link', { name: '본문으로 건너뛰기' })
  await skip.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#parent-main')).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
