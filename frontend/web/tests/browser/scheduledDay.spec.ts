import { test, expect } from '@playwright/test'

test('다른 날 푼 문제의 예정 요일만 보이며 이전 리포트는 유지한다 @responsive', async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await page.goto('/parent/report')
  await page.getByRole('button', { name: '리포트 자세히 보기', exact: false }).click()
  await page.getByLabel('리포트 종류').selectOption('DAILY')
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
  await page.locator('.parent-report-grid').getByRole('button', { name: '자세히 보기', exact: true }).first().click()
  await page.getByRole('button', { name: '활동 기록', exact: true }).click()
  for (const summary of await page.locator('details.report-answer-comparison > summary').all()) await summary.click()
  await expect(page.getByText('화요일 문제 · 목요일에 풀었어요', { exact: true })).toBeVisible()
  await expect(page.getByText('월요일 문제 · 목요일에 풀었어요', { exact: true })).toBeVisible()
  for (const title of ['당일 문제', '추가 문제', '이전 리포트 문제']) {
    const card = page.locator('details.report-answer-comparison').filter({ has: page.locator('summary').getByText(title, { exact: true }) })
    await expect(card).toBeVisible()
    await expect(card.getByText(/에 풀었어요/)).toHaveCount(0)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
