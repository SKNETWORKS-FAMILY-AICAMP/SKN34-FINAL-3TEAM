import { test, expect } from '@playwright/test'

// #803 학부모 일일 리포트 문제별 생각·작성 시간(P28). 원문 비공개여도 시간은 보이고, 시간 없는 답은 줄을 생략한다.
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

test('일일 리포트 문제별로 답변마다 생각·작성 시간을 보이고 원문 비공개에도 남긴다 @responsive', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await page.goto('/parent/report')
  await page.locator('.report-period-picker > summary').click()
  await page.getByRole('button', { name: '일일', exact: true }).click()
  // 시연 목 저장소의 일일 리포트에 report 상세 모양의 문제 하나를 넣는다(원문 비공개, 2번째 답은 시간 없음)
  await page.evaluate(async () => {
    const { reports } = await import('/src/mocks/fixtures/parent.ts' as string)
    for (const versions of reports.values()) for (const r of versions) if (r.periodType === 'DAILY') {
      r.state = 'OK'
      r.problems = [{
        missionId: 'm-803', attemptId: 'a-803', title: '합성 시간 문제', context: 'THEME_DAY', judgment: 'PARTIAL',
        followups: [], finalAnswer: null, elements: [], reflection: null, quotes: [],
        answerTimes: [
          { version: 1, thinkingSeconds: 45, writingSeconds: 130 },
          { version: 3, thinkingSeconds: 600, writingSeconds: 60 },
        ],
      }]
    }
  })
  await page.getByRole('list', { name: '리포트 일자' }).getByRole('button').first().click()
  const problem = page.locator('details.report-answer-comparison').filter({ hasText: '합성 시간 문제' })
  await problem.locator('summary').click()
  await expect(problem.getByText('처음 답: 생각 1분 미만 · 작성 2분', { exact: true })).toBeVisible()
  await expect(problem.getByText('두 번째 되묻기 뒤 답: 생각 10분 · 작성 1분', { exact: true })).toBeVisible()
  await expect(problem.getByText(/^되묻기 뒤 답:/)).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
