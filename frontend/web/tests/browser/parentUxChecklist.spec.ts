import { test, expect, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/parent\/journal/)
}

test('report download preserves the selected format and error reporting keeps the report ID @responsive', async ({ page }, info) => {
  await login(page)
  await page.goto('/parent/report?childId=demo-seoyun')
  await page.getByRole('button', { name: '리포트 다운로드', exact: true }).waitFor()
  await page.evaluate(() => {
    const original = window.fetch.bind(window)
    const audit = window as unknown as { downloadFormats: string[]; reportId: string }
    audit.downloadFormats = []
    window.fetch = (input, init) => {
      const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.href)
      if (/\/reports\/[^/]+\/download$/.test(url.pathname)) {
        audit.downloadFormats.push(url.searchParams.get('format') ?? '')
        audit.reportId = url.pathname.split('/').at(-2) ?? ''
        // An expired link exercises the visible failure state without navigating to a file.
        return Promise.resolve(Response.json({ url: '/test-expired-download', expiresAt: '2000-01-01T00:00:00Z' }))
      }
      return original(input, init)
    }
  })
  const format = page.getByRole('combobox', { name: '리포트 다운로드 형식' })
  await expect(format).toHaveValue('pdf')
  await format.selectOption('md')
  await page.getByRole('button', { name: '리포트 다운로드', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '다운로드 주소가 만료되었습니다.' })).toBeVisible()
  await format.selectOption('pdf')
  await page.getByRole('button', { name: '리포트 다운로드', exact: true }).click()
  await expect.poll(() => page.evaluate(() => (window as unknown as { downloadFormats: string[] }).downloadFormats)).toEqual(['md', 'pdf'])
  await page.locator('.report-help-actions summary').click()
  const reportLink = page.locator('.report-help-actions a')
  const href = await reportLink.getAttribute('href')
  expect(href).toContain('targetType=REPORT')
  expect(new URL(href!, 'http://localhost').searchParams.get('targetId')).toBe(await page.evaluate(() => (window as unknown as { reportId: string }).reportId))
  await expect(page.getByRole('button', { name: '리포트 전체 보기', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.screenshot({ path: info.outputPath('report-download-and-help.png') })
  await reportLink.click()
  await expect(page).toHaveURL(/\/parent\/support\?.*targetType=REPORT/)
})

test('billing comparison is reachable from the top without replacing the premium offer @responsive', async ({ page }) => {
  await login(page)
  await page.goto('/parent/billing?childId=demo-seoyun')
  await expect(page.getByRole('region', { name: '프리미엄 이용권', exact: true })).toBeVisible()
  await page.locator('.premium-header-actions').getByRole('link', { name: '무료·프리미엄 비교', exact: true }).click()
  await expect(page).toHaveURL(/childId=demo-seoyun#plan-compare$/)
  await expect(page.locator('#plan-compare')).toBeVisible()
  await expect(page.locator('.premium-comparison')).toHaveAttribute('open', '')
})

test('the 51st memory book is reachable and the original question appears before answers', async ({ page }) => {
  await login(page)
  const guide = page.getByRole('dialog', { name: '학부모 첫 사용 안내' })
  if (await guide.isVisible()) await guide.getByRole('button', { name: '건너뛰기' }).click()
  await page.getByRole('button', { name: /생각 활동 전체 보기/ }).click()
  await page.getByRole('button', { name: '원문 보기 ↗', exact: true }).first().click()
  await expect(page.locator('.pd-original-question p')).not.toBeEmpty()
  await page.keyboard.press('Escape')
  await page.evaluate(() => {
    const original = window.fetch.bind(window)
    window.fetch = (input, init) => {
      const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.href)
      if (url.pathname.endsWith('/memory-books/rounds')) {
        const current = Number(url.searchParams.get('page') ?? 0), size = 50
        const all = Array.from({ length: 51 }, (_, i) => {
          const date = new Date('2026-11-23T00:00:00Z'); date.setUTCDate(date.getUTCDate() - i * 7)
          return { themeId: `test-theme-${i}`, weekStart: date.toISOString().slice(0, 10), title: `검증 이야기 ${i + 1}`, imageUrl: null, book: null }
        })
        return Promise.resolve(Response.json({ items: all.slice(current * size, (current + 1) * size), page: current, size, totalElements: 51, canCreate: true, lockedCount: 0 }))
      }
      return original(input, init)
    }
    history.pushState({}, '', '/parent/report?childId=demo-seoyun'); dispatchEvent(new PopStateEvent('popstate'))
  })
  const pager = page.getByRole('navigation', { name: '그림책 책장 페이지' })
  await pager.getByRole('button', { name: '다음 회차' }).click()
  await expect(page.getByText('검증 이야기 51', { exact: true })).toBeVisible()
  await expect(pager.getByRole('button', { name: '다음 회차' })).toBeDisabled()
  await pager.getByRole('button', { name: '이전 회차' }).click()
  await expect(page.getByText('검증 이야기 1', { exact: true })).toBeVisible()
})

test('failed onboarding save stays visible and can be retried', async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    let failed = false
    window.fetch = (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/me/onboarding') && init?.method === 'PUT' && !failed) {
        failed = true
        return Promise.resolve(Response.json({ status: 503, title: '테스트 저장 실패' }, { status: 503 }))
      }
      return original(input, init)
    }
  })
  await login(page)
  const guide = page.getByRole('dialog', { name: '학부모 첫 사용 안내' })
  await guide.getByRole('button', { name: '건너뛰기' }).click()
  await expect(guide.getByRole('alert')).toContainText('안내 완료를 저장하지 못했어요')
  await guide.getByRole('button', { name: '건너뛰기' }).click()
  await expect(guide).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: '서윤의 학습 현황', exact: true })).toBeVisible()
  await expect(guide).toHaveCount(0)
})

test('unknown parent URLs show a recovery link @responsive', async ({ page }) => {
  await login(page)
  await page.goto('/parent/not-a-real-page')
  await expect(page.getByRole('heading', { name: '페이지를 찾을 수 없어요' })).toBeVisible()
  await page.getByRole('link', { name: '학습 현황으로', exact: true }).click()
  await expect(page.getByRole('heading', { name: '서윤의 학습 현황', exact: true })).toBeVisible()
})

test('failed workspace module provides Korean recovery actions', async ({ page, context }) => {
  await context.route(/\/src\/presentation\/parent\/ParentWorkspace\.tsx(?:\?.*)?$/, route => route.abort('failed'))
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page.getByRole('heading', { name: '화면을 불러오지 못했어요' })).toBeVisible()
  await expect(page.getByRole('button', { name: '다시 불러오기' })).toBeVisible()
  await expect(page.getByRole('link', { name: '처음 화면으로' })).toBeVisible()
  await expect(page.getByText('Unexpected Application Error!')).toHaveCount(0)
})
