import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

async function login(page: Page, email = 'admin@example.test') {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill(email)
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await expect(page.getByRole('heading', { name: '운영 요약', exact: true })).toBeVisible()
}
async function openMenu(page: Page) {
  const button = page.getByRole('button', { name: '메뉴', exact: true })
  if (await button.isVisible()) await button.click()
}
async function navigate(page: Page, label: string) {
  await openMenu(page)
  await page.getByRole('navigation', { name: '관리자 메뉴' }).getByRole('link', { name: label, exact: true }).click()
}

test('메뉴 검색은 승인된 메뉴만 찾고 이동 후 모바일 메뉴를 닫는다 @responsive', async ({ page }) => {
  await login(page, 'ops@example.test')
  await openMenu(page)
  const nav = page.getByRole('navigation', { name: '관리자 메뉴' })
  await page.getByLabel('관리자 메뉴 찾기').fill('결제')
  await expect(nav.getByRole('link')).toHaveCount(0)
  await expect(page.getByText('일치하는 메뉴가 없습니다.')).toBeVisible()
  await page.getByLabel('메뉴 검색 지우기').click()
  await page.getByLabel('관리자 메뉴 찾기').fill('모델')
  await expect(nav.getByRole('link')).toHaveCount(1)
  await nav.getByRole('link', { name: '모델·프롬프트', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/models/)
  await expect(page.getByRole('heading', { name: '모델·프롬프트 버전', exact: true })).toBeVisible()
  const button = page.getByRole('button', { name: '메뉴', exact: true })
  if (await button.isVisible()) {
    await expect(button).toHaveAttribute('aria-expanded', 'false')
    await button.click()
    await page.keyboard.press('Escape')
    await expect(button).toBeFocused()
    await expect(nav).toBeHidden()
    await button.click()
    await page.getByRole('button', { name: '메뉴 바깥 닫기' }).click({ position: { x: 350, y: 100 } })
    await expect(nav).toBeHidden()
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('낮은 화면에서 관리자 프로필을 열고 닫거나 마지막 메뉴로 스크롤해도 프로필은 하단에 남는다 @responsive', async ({ page }) => {
  await page.setViewportSize({ ...page.viewportSize()!, height: 420 })
  await login(page, 'ops@example.test')
  await openMenu(page)
  const profile = page.locator('details.ad-sidebar-profile')
  const summary = profile.getByLabel('관리자 계정 및 권한 안내')
  const permissions = profile.getByText('서비스 운영', { exact: true })
  const scroller = page.locator('.ad-nav-scroll')
  const nav = scroller.getByRole('navigation', { name: '관리자 메뉴' })
  const last = nav.getByRole('link').last()
  await expect(last).toHaveAccessibleName('표현 검토')
  await expect(nav.getByRole('link')).toHaveCount(9)
  await expect(summary).toContainText('이용 가능한 메뉴 9개')
  await expect(summary).toBeInViewport({ ratio: 1 })
  await expect(permissions).toBeHidden()
  await summary.focus()
  await summary.press('Enter')
  await expect(profile.getByText('승인 권한', { exact: true })).toBeVisible()
  await expect(permissions).toBeVisible()
  await summary.press('Enter')
  await expect(permissions).toBeHidden()

  const footerTop = (await profile.boundingBox())!.y
  await expect.poll(() => scroller.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true)
  await last.scrollIntoViewIfNeeded()
  await expect.poll(() => scroller.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  await expect(last).toBeInViewport({ ratio: 1 })
  await expect(summary).toBeInViewport({ ratio: 1 })
  expect((await profile.boundingBox())!.y).toBe(footerTop)
  await last.click()
  await expect(page).toHaveURL(/\/admin\/expressions/)
})

test('주간 테마 요청을 취소하면 목록 필터를 유지하고 새 요청을 빈 양식으로 연다 @responsive', async ({ page }) => {
  await login(page)
  await navigate(page, '주간 테마 검수')
  const shelf = page.getByRole('region', { name: '주간 테마 목록', exact: true })
  const gradeFilter = shelf.getByLabel('학년 선택')
  const request = page.getByRole('button', { name: '테마 추가 생성 요청' })
  const dialog = page.getByRole('dialog', { name: '테마 추가 생성 요청' })
  await gradeFilter.selectOption('G4')
  await request.click()
  await expect(dialog.getByLabel('생성 학년')).toHaveValue('G4')
  await dialog.getByLabel('테마 주제 키워드').fill('우리 동네 도서관')
  await dialog.getByRole('button', { name: '취소' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(gradeFilter).toHaveValue('G4')
  await request.click()
  await expect(dialog.getByLabel('테마 주제 키워드')).toHaveValue('')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('환불 검토는 상세 패널에서 확인하고 명시적 확정 전에는 요청하지 않는다 @responsive', async ({ page }) => {
  await login(page)
  await navigate(page, '결제·환불')
  await expect(page.getByLabel('집계 시작일')).toHaveCount(0)
  await page.getByLabel('현재 페이지 환불 검색').fill('demo-refund-1')
  const select = page.getByRole('button', { name: 'demo-refund-1 환불 선택', exact: true })
  await expect(page.getByRole('button', { name: 'demo-refund-2 환불 선택', exact: true })).toHaveCount(0)
  const requests: string[] = []
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/refund-requests/')) requests.push(r.url()) })
  await select.click()
  const dialog = page.getByRole('dialog', { name: '환불 검토', exact: true })
  await expect(dialog).toBeVisible()
  const approve = dialog.getByRole('button', { name: '환불 승인 요청', exact: true })
  await expect(approve).toBeDisabled()
  for (const check of await dialog.getByRole('checkbox').all()) await check.check()
  await approve.click()
  await expect(dialog.getByRole('button', { name: '처리 확정', exact: true })).toBeVisible()
  expect(requests).toEqual([])
  await dialog.getByRole('button', { name: '취소', exact: true }).click()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(select).toBeFocused()
  await page.getByRole('button', { name: '거래 내역', exact: true }).click()
  await expect(page.getByLabel('집계 시작일')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('감사 이력 검색과 결과 필터를 초기화하면 원래 목록이 유지된다 @responsive', async ({ page }) => {
  await login(page)
  await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/admin/operations.ts'
    const { audits } = await import(path)
    const createdAt = new Date().toISOString()
    audits.push(
      { id: 'test-audit-model', actorUserId: 'test-ops', action: 'MODEL_ACTIVATE', targetType: 'MODEL_VERSION', targetId: 'prompt-1', result: 'SUCCESS', createdAt, detail: { scopes: ['judgment/grade-3/narrative'] } },
      { id: 'test-audit-job', actorUserId: 'test-ops', action: 'JOB_RETRY', targetType: 'REPORT', targetId: 'job-1', result: 'FAILURE', createdAt },
      { id: 'test-audit-mission', actorUserId: 'test-ops', action: 'MISSION_PUBLISH', targetType: 'MISSION', targetId: 'mission-1', result: 'SUCCESS', createdAt },
    )
  })
  await navigate(page, '감사 이력')
  const search = page.getByLabel('조회된 감사 이력 검색')
  const table = page.getByRole('table')
  const modelRow = table.getByRole('row').filter({ hasText: '모델 버전 활성화' })
  await expect(modelRow).toBeVisible()
  const count = await table.locator('tbody tr').count()
  await search.fill('모델 버전 활성화')
  await expect(table.locator('tbody tr')).toHaveCount(1)
  await search.fill('MODEL_ACTIVATE')
  await expect(table.locator('tbody tr')).toHaveCount(1)
  await modelRow.getByText('모델 버전 조치 상세', { exact: true }).click()
  await expect(modelRow.getByText('초등 3학년 · 서술형 판정', { exact: true })).toBeVisible()
  await search.clear()
  await expect(table.getByText('작업 재처리', { exact: true })).toBeVisible()
  await expect(table.getByText('미션 게시', { exact: true })).toBeVisible()
  await search.fill('존재하지않는-감사기록')
  await expect(page.getByText('검색 조건에 맞는 이력이 없습니다.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '검색 초기화', exact: true }).click()
  await expect(search).toHaveValue('')
  await expect(page.locator('.ad-audit-ledger tbody tr')).toHaveCount(count)
  await page.getByRole('button', { name: '실패', exact: true }).click()
  await expect(page.locator('.ad-audit-ledger tbody .ad-badge').filter({ hasText: '성공' })).toHaveCount(0)
  await page.getByRole('button', { name: '전체 결과', exact: true }).click()
  await expect(page.locator('.ad-audit-ledger tbody tr')).toHaveCount(count)
})

test('문의함과 공지 작업을 분리하고 상세 창을 키보드로 닫는다 @responsive', async ({ page }) => {
  await login(page)
  await navigate(page, '문의·공지')
  await expect(page.getByRole('button', { name: '새 공지', exact: true })).toHaveCount(0)
  const inquiry = page.getByRole('button', { name: '학습 기록은 어디서 확인하나요? 문의 선택', exact: true })
  await inquiry.click()
  const dialog = page.getByRole('dialog', { name: '문의 답변', exact: true })
  await expect(dialog.getByLabel('문의 답변', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(inquiry).toBeFocused()
  await page.getByRole('button', { name: '공지·점검', exact: true }).click()
  await page.getByRole('button', { name: '새 공지', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '공지 작성', exact: true }).getByLabel('공지 제목')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: '새 공지', exact: true })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('알림은 한국 시각과 읽음 상태를 구분하고 화면 안에 표시한다 @responsive', async ({ page }) => {
  await login(page)
  const bell = page.getByRole('button', { name: '알림 열기', exact: true })
  await bell.click()
  const dialog = page.getByRole('dialog', { name: '알림', exact: true })
  await expect(dialog.locator('.notification-meta time').first()).toHaveText(/^\d{4}년 \d{1,2}월 \d{1,2}일 \d{2}:\d{2}$/)
  await expect(dialog.locator('.notification-read-state').first()).toHaveText(/읽음|읽지 않음/)
  expect(await dialog.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(false)
  const box = await dialog.boundingBox()
  const viewport = page.viewportSize()!
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.y).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1)
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1)
  await page.setViewportSize({ ...viewport, height: 560 })
  await dialog.getByRole('button', { name: '수신 설정', exact: true }).click()
  const body = dialog.getByRole('region', { name: '알림 내용' })
  const thumb = dialog.locator('.cj-modal-scroll-marker')
  await expect.poll(() => body.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true)
  await expect(thumb).toHaveCSS('opacity', '0')
  const close = dialog.getByRole('button', { name: '창 닫기' })
  const headerY = (await close.boundingBox())!.y
  await body.hover()
  await page.mouse.wheel(0, 250)
  await expect(thumb).toHaveAttribute('data-visible', 'true')
  await expect.poll(() => body.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  expect((await close.boundingBox())!.y).toBe(headerY)
  await expect(thumb).toHaveCSS('opacity', '0')
  await body.press('End')
  await expect(dialog.getByRole('button', { name: '설정 저장', exact: true })).toBeInViewport()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(bell).toBeFocused()
})

test('작업 필터는 선택 문구와 화살표 공간을 분리한다 @responsive', async ({ page }) => {
  await login(page)
  await navigate(page, '작업 재처리')
  for (const name of ['작업 유형', '작업 상태']) {
    const select = page.getByLabel(name, { exact: true })
    for (const value of ['', name === '작업 유형' ? 'NOTIFICATION' : 'RUNNING']) {
      await select.selectOption(value)
      const fit = await select.evaluate((el: HTMLSelectElement) => {
        const s = getComputedStyle(el), context = document.createElement('canvas').getContext('2d')!
        context.font = s.font
        return { text: context.measureText(el.selectedOptions[0].text).width,
          available: el.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight),
          arrowSpace: parseFloat(s.paddingRight) }
      })
      expect(fit.available + 1).toBeGreaterThanOrEqual(fit.text)
      expect(fit.arrowSpace).toBeGreaterThanOrEqual(40)
    }
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('관리자 메뉴의 정보 영역은 화면 폭 안에 유지된다 @responsive', async ({ page }, testInfo) => {
  test.setTimeout(60_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await login(page)
  await openMenu(page)
  const nav = page.getByRole('navigation', { name: '관리자 메뉴' })
  await expect(nav.getByText('워크스페이스', { exact: true })).toBeVisible()
  await expect(nav.getByText('콘텐츠 관리', { exact: true })).toBeVisible()
  const menu = nav.getByRole('link')
  const firstLinks = ['운영 홈', '감사 이력', '주간 테마 검수', '게시 관리', '미션 관리', '미션 초안', '꾸미기 아이템']
  for (const [index, label] of firstLinks.entries()) await expect(menu.nth(index)).toHaveAccessibleName(label)
  await nav.getByRole('link', { name: '운영 홈', exact: true }).click()
  for (const [label, path] of [
    ['운영 홈', 'home'], ['감사 이력', 'audit'], ['주간 테마 검수', 'theme-drafts'], ['게시 관리', 'themes'],
    ['미션 관리', 'missions'], ['미션 초안', 'mission-drafts'], ['꾸미기 아이템', 'looks'],
    ['작업 재처리', 'jobs'], ['작업 대기열', 'queues'], ['오류 신고', 'errors'], ['문의·공지', 'support'],
    ['모델·프롬프트', 'models'], ['표현 검토', 'expressions'], ['AI 사용량', 'usage'], ['결제·환불', 'payments'],
  ]) {
    await navigate(page, label)
    await expect(page.locator('#admin-main h1')).toBeVisible()
    await expect(page.getByText('불러오고 있습니다.', { exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), path).toBe(false)
    await page.screenshot({ path: testInfo.outputPath(`${path}.png`), fullPage: true })
  }
  expect(errors).toEqual([])
})
