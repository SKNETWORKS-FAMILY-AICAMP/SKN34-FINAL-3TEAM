import { test, expect } from '@playwright/test'

test('다른 날 푼 문제의 예정 요일만 보이며 이전 리포트는 유지한다 @responsive', async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await page.goto('/parent/report')
  await page.locator('.report-period-picker > summary').click()
  await page.getByRole('button', { name: '일일', exact: true }).click()
  await page.evaluate(async () => {
    const { reports } = await import('/src/mocks/fixtures/parent.ts' as string)
    for (const versions of reports.values()) for (const r of versions) if (r.periodType === 'DAILY') {
      r.state = 'OK'
      r.period = { from: '2026-11-19', to: '2026-11-19' }
      r.problems = [
        { title: '늦게 푼 문제', context: 'THEME_DAY', scheduledDay: 'TUE' },
        { title: '다시 푼 문제', context: 'THEME_REVIEW', scheduledDay: 'MON' },
        { title: '당일 문제', context: 'THEME_DAY', scheduledDay: 'THU' },
        { title: '추가 문제', context: 'EXTRA', scheduledDay: null },
        { title: '이전 리포트 문제', context: 'THEME_DAY' },
      ].map((p, i) => ({ missionId: `m-${i}`, attemptId: `a-${i}`, judgment: 'PARTIAL', followups: [], finalAnswer: null, elements: [], reflection: null, quotes: [], ...p }))
    }
  })
  await page.getByRole('list', { name: '리포트 일자' }).getByRole('button').first().click()
  await page.getByRole('button', { name: '전체 5개 보기', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  const seen: number[] = []
  await expect(page.locator('[data-daily-group]:enabled').first()).toBeVisible()
  const groups = await dialog.locator('[data-daily-group]:enabled').count()
  for (let g = 0; g < groups; g++) {
    await dialog.locator('[data-daily-group]:enabled').nth(g).click()
    const indices = await dialog.locator('[data-daily-problem-link]').evaluateAll(els => els.map(e => Number(e.getAttribute('data-daily-problem-link'))))
    for (const index of indices) {
      await dialog.locator(`[data-daily-problem-link="${index}"]`).click()
      const card = dialog.locator('[data-daily-problem-index]')
      if (index < 2) await expect(card.getByText(`${index === 0 ? '화' : '월'}요일 문제 · 목요일에 풀었어요`, { exact: true })).toBeVisible()
      else await expect(card.getByText(/에 풀었어요/)).toHaveCount(0)
      seen.push(index)
      await dialog.getByRole('navigation', { name: '문제 탐색 경로' }).getByRole('button').nth(1).click()
    }
    await dialog.getByRole('button', { name: '전체 리포트', exact: true }).click()
  }
  expect(seen.sort()).toEqual([0, 1, 2, 3, 4])
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
