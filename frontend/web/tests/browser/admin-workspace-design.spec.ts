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

test('초안 요청 양식을 접었다 열어도 작성 중인 값과 목록은 유지한다 @responsive', async ({ page }) => {
  await login(page)
  await openMenu(page)
  await page.getByRole('navigation', { name: '관리자 메뉴' }).getByRole('link', { name: '테마 초안', exact: true }).click()
  await expect(page.getByLabel('테마 주제 키워드')).toBeHidden()
  await page.getByText('새 테마 초안 요청', { exact: true }).click()
  await page.getByLabel('테마 주제 키워드').fill('우리 동네 도서관')
  const panel = page.locator('.ad-request-panel')
  await panel.locator(':scope > summary').click()
  await expect(page.getByLabel('테마 주제 키워드')).toBeHidden()
  await expect(page.getByRole('heading', { name: '테마 초안 목록', exact: true })).toBeVisible()
  await page.getByLabel('테마 초안 상태', { exact: true }).selectOption('READY')
  await expect(page.getByLabel('테마 주제 키워드')).toBeHidden()
  await panel.locator(':scope > summary').click()
  await expect(page.getByLabel('테마 주제 키워드')).toHaveValue('우리 동네 도서관')
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
  await navigate(page, '감사 이력')
  const search = page.getByLabel('조회된 감사 이력 검색')
  await expect(page.getByRole('table')).toBeVisible()
  const count = await page.locator('.ad-audit-ledger tbody tr').count()
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
  for (const [label, path] of [
    ['운영 현황', 'home'], ['감사 이력', 'audit'], ['미션 관리', 'missions'], ['미션 초안', 'mission-drafts'],
    ['주간 테마', 'themes'], ['테마 초안', 'theme-drafts'], ['꾸미기 아이템', 'looks'],
    ['작업 재처리', 'jobs'], ['큐·DLQ', 'queues'], ['오류 신고', 'errors'], ['문의·공지', 'support'],
    ['모델·프롬프트', 'models'], ['AI 사용량', 'usage'], ['결제·환불', 'payments'],
  ]) {
    await navigate(page, label)
    await expect(page.locator('#admin-main h1')).toBeVisible()
    await expect(page.getByText('불러오고 있습니다.', { exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), path).toBe(false)
    await page.screenshot({ path: testInfo.outputPath(`${path}.png`), fullPage: true })
  }
  expect(errors).toEqual([])
})
