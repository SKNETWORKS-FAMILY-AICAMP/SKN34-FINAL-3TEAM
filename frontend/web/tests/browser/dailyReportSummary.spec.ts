import { test, expect, type Page } from '@playwright/test'

async function openDaily(page: Page, mode: 'normal' | 'private' | 'empty' = 'normal') {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await page.evaluate(async sharing => {
    const { saveSharing } = await import('/src/mocks/fixtures/sharing.ts' as string)
    saveSharing('demo-seoyun', sharing)
  }, mode !== 'private')
  await page.goto('/parent/report?childId=demo-seoyun')
  await page.getByRole('button', { name: '리포트 자세히 보기', exact: false }).click()
  await page.getByLabel('리포트 종류').selectOption('DAILY')
  await page.evaluate(async mode => {
    const { reports } = await import('/src/mocks/fixtures/parent.ts' as string)
    for (const versions of reports.values()) for (const report of versions) if (report.periodType === 'DAILY') {
      report.state = mode === 'empty' ? 'NO_RECORD' : 'OK'
      report.problems = mode === 'empty' ? [] : Array.from({ length: 15 }, (_, i) => ({
        missionId: `summary-${i}`, attemptId: `attempt-${i}`, title: i === 13 ? '다른 의견을 듣고 우리 동네의 문제를 함께 해결하려면 어떻게 해야 할까요?' : ['우리 동네에 도서관이 필요한 까닭', '분리수거를 더 쉽게 하는 방법', '친구와 의견이 다를 때'][i % 3],
        context: 'EXTRA', judgment: i < 8 ? 'CORRECT' : i < 13 ? 'PARTIAL' : 'RETHINK',
        followups: [{ question: '그렇게 생각한 까닭은 무엇인가요?', answer: null }],
        finalAnswer: '서로의 의견을 듣고 근거를 비교해요.',
        elements: [{ label: ['근거', '주장', '생각이 달라진 까닭', '해결할 문제 정하기', '실천 결과 확인하기', '경험과 연결하기'][i % 6], satisfied: true }],
        reflection: { written: true, difficulty: i < 8 ? 'EASY' : i < 14 ? 'NORMAL' : 'HARD', text: '근거를 먼저 생각했어요.' }, quotes: [],
      }))
    }
  }, mode)
  await page.locator('.parent-report-grid').getByRole('button', { name: '자세히 보기', exact: true }).first().click()
  const summary = page.getByLabel('일일 리포트 요약', { exact: true })
  await expect(summary).toBeVisible()
  return summary
}

test('daily summary shows report facts and opens matching activities @responsive', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  const summary = await openDaily(page)
  await expect(summary.getByRole('region', { name: '오늘 완료한 활동', exact: true })).toContainText('15개')
  await expect(summary.locator('.daily-judgments')).toContainText('8개맞게 썼어요')
  await expect(summary.locator('.daily-judgments')).toContainText('5개일부 확인')
  await expect(summary.locator('.daily-judgments')).toContainText('2개다시 생각해 보기')
  await expect(summary.getByRole('region', { name: '되묻기에 대한 답변 기록', exact: true })).toContainText('0개')
  await expect(summary.locator('.daily-difficulty-legend')).toContainText('쉬웠어요8개보통6개어려웠어요1개기록 없음0개')
  await page.getByRole('region', { name: '리포트 내용', exact: true }).evaluate(el => { el.scrollTop = 0 })
  await page.screenshot({ path: info.outputPath('daily-summary.png') })
  await summary.locator('.daily-difficulty').scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('daily-summary-bottom.png') })
  expect(await summary.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await summary.getByRole('region', { name: '다시 살펴볼 활동', exact: true }).getByRole('button').first().click()
  const selected = page.locator('[data-daily-problem-index="13"]')
  await expect(selected).toHaveAttribute('open', '')
  await expect(selected.locator('summary')).toBeFocused()
  await expect(selected).toContainText('서로의 의견을 듣고 근거를 비교해요.')
  await page.getByRole('button', { name: '요약', exact: true }).click()
  await summary.getByRole('region', { name: '오늘 확인된 생각 요소', exact: true }).getByRole('button', { name: /^근거/ }).click()
  for (const index of [0, 6, 12]) await expect(page.locator(`[data-daily-problem-index="${index}"]`)).toHaveAttribute('open', '')
  await page.getByRole('button', { name: '요약', exact: true }).click()
  await summary.getByRole('button', { name: '전체 15개 보기', exact: true }).click()
  await expect(page.locator('.report-section:visible')).toContainText('그날 푼 문제')
  expect(errors).toEqual([])
})

test('private daily summary keeps numeric records and labels hidden follow-up counts @responsive', async ({ page }) => {
  const summary = await openDaily(page, 'private')
  await expect(summary.getByRole('region', { name: '되묻기가 있었던 활동', exact: true })).toContainText('원문 비공개')
  await expect(summary.getByRole('region', { name: '되묻기에 대한 답변 기록', exact: true })).not.toContainText('0개')
  await expect(summary.getByRole('region', { name: '돌아보기를 작성한 활동', exact: true })).toContainText('15개')
  await expect(summary.locator('.daily-difficulty-legend')).toContainText('쉬웠어요8개')
})

test('empty daily summary has an honest empty state without an invented chart @responsive', async ({ page }) => {
  const summary = await openDaily(page, 'empty')
  await expect(summary).toContainText('이날은 완료한 활동이 없어요.')
  await expect(summary.locator('.daily-donut')).toHaveCount(0)
  await expect(summary.getByRole('region', { name: '오늘 완료한 활동', exact: true })).toContainText('0개')
})
