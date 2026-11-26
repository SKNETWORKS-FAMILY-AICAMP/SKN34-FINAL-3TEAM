import { test, expect, type Page } from '@playwright/test'

async function openDaily(page: Page, mode: 'normal' | 'private' | 'empty' | 'missing' | 'single-element' = 'normal') {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await page.evaluate(async sharing => {
    const { saveSharing } = await import('/src/mocks/fixtures/sharing.ts' as string)
    saveSharing('demo-seoyun', sharing)
  }, mode !== 'private')
  await page.goto('/parent/report?childId=demo-seoyun')
  await page.locator('.report-period-picker > summary').click()
  await page.getByRole('button', { name: '일일', exact: true }).click()
  // Wait for the daily list request to populate the fixture before replacing its reports.
  await expect(page.getByRole('list', { name: '리포트 일자' }).getByRole('button').first()).toHaveText(/^\d{4}-\d{2}-\d{2}$/)
  await page.evaluate(async mode => {
    const { reports } = await import('/src/mocks/fixtures/parent.ts' as string)
    for (const versions of reports.values()) for (const report of versions) if (report.periodType === 'DAILY') {
      report.state = mode === 'empty' ? 'NO_RECORD' : 'OK'
      report.problems = mode === 'empty' ? [] : Array.from({ length: 15 }, (_, i) => ({
        missionId: `summary-${i}`, attemptId: `attempt-${i}`, title: i === 13 ? '다른 의견을 듣고 우리 동네의 문제를 함께 해결하려면 어떻게 해야 할까요?' : ['우리 동네에 도서관이 필요한 까닭', '분리수거를 더 쉽게 하는 방법', '친구와 의견이 다를 때'][i % 3],
        context: i < 5 ? 'THEME_DAY' : 'EXTRA', judgment: i < 8 ? 'CORRECT' : i < 13 ? 'PARTIAL' : 'RETHINK',
        theme: i < 5 ? { themeId: 'theme', versionId: 'version-1', title: '우리 동네', storyType: 'LOST' } : null,
        followups: [{ question: '그렇게 생각한 까닭은 무엇인가요?', answer: null }],
        finalAnswer: '서로의 의견을 듣고 근거를 비교해요.',
        elements: [{ label: ['근거', '주장', '생각이 달라진 까닭', '해결할 문제 정하기', '실천 결과 확인하기', '경험과 연결하기'][i % 6], satisfied: true }],
        reflection: { written: true, difficulty: i < 8 ? 'EASY' : i < 14 ? 'NORMAL' : 'HARD', text: '근거를 먼저 생각했어요.' }, quotes: [],
      }))
      report.thinkingTypes = ['ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT'].map((type, n) => ({
        type, state: 'OK', missions: report.problems.filter((_: unknown, i: number) => i % 5 === n).map((p: { attemptId: string; title: string }) => ({ attemptId: p.attemptId, title: p.title })),
      }))
      report.themeSummary = null
      if (mode === 'single-element') {
        for (const [index, problem] of report.problems.entries()) {
          problem.elements = index === 0 ? [{ label: '근거', satisfied: true }] : []
        }
      }
      if (mode === 'missing') {
        report.problems[0].reflection = null
        report.problems[1].reflection!.difficulty = 'UNKNOWN_LEVEL'
        report.problems[2].reflection!.written = false
      }
    }
  }, mode)
  await page.getByRole('list', { name: '리포트 일자' }).getByRole('button').first().click()
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
  const correctBadge = await summary.locator('.daily-activities .daily-badge').first().boundingBox()
  const rethinkBadge = await summary.locator('.daily-review .daily-badge').first().boundingBox()
  expect(correctBadge!.x).toBeCloseTo(rethinkBadge!.x, 0)
  await summary.scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('daily-summary.png') })
  await summary.locator('.daily-difficulty').scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('daily-summary-bottom.png') })
  expect(await summary.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.locator('[data-daily-problem-index]')).toHaveCount(0)
  const review = summary.getByRole('region', { name: '다시 살펴볼 활동', exact: true }).getByRole('button').first()
  await review.click()
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  await expect(dialog).toBeVisible()
  const selected = page.locator('[data-daily-problem-index="13"]')
  await expect(selected).toBeVisible()
  await expect(dialog.locator('.daily-navigation-heading')).toBeFocused()
  await expect(dialog.getByRole('navigation', { name: '문제 탐색 경로' })).toContainText('추가 문제')
  await expect(dialog.getByRole('navigation', { name: '문제 탐색 경로' })).not.toContainText('문제 해결하기')
  await expect(selected).toContainText('서로의 의견을 듣고 근거를 비교해요.')
  await expect(selected.locator('.report-reader-document')).toContainText('서로의 의견을 듣고 근거를 비교해요.')
  await expect(selected.getByRole('complementary', { name: '판정과 돌아보기' })).toContainText('다시 생각해 보기')
  await expect(selected.getByRole('complementary', { name: '판정과 돌아보기' })).not.toContainText('서로의 의견을 듣고 근거를 비교해요.')
  expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  await page.screenshot({ path: info.outputPath('daily-problems-dialog.png') })
  const back = dialog.getByRole('button', { name: '뒤로 가기', exact: true })
  const forward = dialog.getByRole('button', { name: '앞으로 가기', exact: true })
  await expect(forward).toBeDisabled()
  await back.click()
  await expect(dialog.locator('[data-daily-problem-link="13"]')).toBeVisible()
  await forward.click()
  await expect(selected).toBeVisible()
  await back.click()
  await dialog.locator('[data-daily-problem-link="14"]').click()
  await expect(forward).toBeDisabled()
  await back.click()
  await back.click()
  await expect(back).toBeDisabled()
  await expect(dialog.locator('[data-daily-story]')).toHaveCount(11)
  await forward.click()
  await forward.click()
  await expect(dialog.locator('[data-daily-problem-index="14"]')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(review).toBeFocused()
  expect(errors).toEqual([])
})

test('element links open matching problems directly and retain the theme path @responsive', async ({ page }, info) => {
  const summary = await openDaily(page)
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  await summary.getByRole('region', { name: '오늘 확인된 생각 요소', exact: true }).getByRole('button', { name: /^근거/ }).click()
  await expect(dialog.locator('[data-daily-problem-index="0"]')).toBeVisible()
  await expect(dialog.locator('.daily-navigation-heading')).toBeFocused()
  const path = dialog.getByRole('navigation', { name: '문제 탐색 경로' })
  const matching = dialog.getByRole('navigation', { name: '선택한 조건의 활동 이동' })
  await expect(path).toContainText('잃어버린 것 찾기')
  await expect(matching).toContainText('1 / 3')
  await expect(matching.getByRole('button', { name: '이전 활동' })).toBeDisabled()
  await page.screenshot({ path: info.outputPath('daily-element-direct.png') })
  for (const index of [6, 12]) {
    await matching.getByRole('button', { name: '다음 활동' }).click()
    await expect(dialog.locator('[data-daily-problem-index]')).toHaveCount(1)
    await expect(dialog.locator(`[data-daily-problem-index="${index}"]`)).toBeVisible()
    await expect(path).toContainText('추가 문제')
    await expect(dialog.locator('.daily-navigation-heading')).toBeFocused()
  }
  await expect(matching).toContainText('3 / 3')
  await expect(matching.getByRole('button', { name: '다음 활동' })).toBeDisabled()
  await matching.getByRole('button', { name: '이전 활동' }).click()
  await expect(dialog.locator('[data-daily-problem-index="6"]')).toBeVisible()
  await path.getByRole('button', { name: '추가 문제', exact: true }).click()
  await expect(dialog.locator('[data-daily-problem-link]')).toHaveCount(2)
  await path.getByRole('button', { name: '전체 리포트', exact: true }).click()
  await expect(dialog.locator('[data-daily-group]:enabled')).toHaveCount(2)
  await expect(dialog.locator('[data-daily-group]:enabled').first()).toContainText('잃어버린 것 찾기')
  await expect(dialog.locator('[data-daily-group]:enabled').last()).toContainText('추가 문제')
  const found: number[] = []
  for (let n = 0; n < 2; n++) {
    await dialog.locator('[data-daily-group]:enabled').nth(n).click()
    found.push(...await dialog.locator('[data-daily-problem-link]').evaluateAll(els => els.map(e => Number(e.getAttribute('data-daily-problem-link')))))
    await dialog.locator('[data-daily-problem-link]').first().click()
    await expect(dialog.locator('[data-daily-problem-index]')).toHaveCount(1)
    await dialog.getByRole('button', { name: '전체 리포트', exact: true }).click()
  }
  expect(found.sort((a,b) => a-b)).toEqual([0, 6, 12])
  await dialog.getByRole('button', { name: '전체 문제 보기', exact: true }).click()
  await expect(dialog.locator('[data-daily-group]:enabled')).toHaveCount(2)
  await expect(dialog.locator('.daily-report-filter')).toHaveCount(0)
  await dialog.getByRole('button', { name: '창 닫기', exact: true }).click()
})

test('an element found in one activity opens that problem without extra navigation @responsive', async ({ page }) => {
  const summary = await openDaily(page, 'single-element')
  const link = summary.getByRole('region', { name: '오늘 확인된 생각 요소', exact: true }).getByRole('button', { name: '근거 1개 활동', exact: true })
  await link.click()
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  await expect(dialog.locator('[data-daily-problem-index="0"]')).toBeVisible()
  await expect(dialog.locator('.daily-navigation-heading')).toBeFocused()
  await expect(dialog.locator('.report-final-answer')).toContainText('서로의 의견을 듣고 근거를 비교해요.')
  await expect(dialog.getByRole('navigation', { name: '선택한 조건의 활동 이동' })).toHaveCount(0)
  await dialog.getByRole('button', { name: '잃어버린 것 찾기', exact: true }).click()
  await expect(dialog.locator('[data-daily-problem-link="0"]')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(link).toBeFocused()
})

test('full report navigates theme to problem and restores keyboard focus @responsive', async ({ page }, info) => {
  const summary = await openDaily(page)
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  await summary.getByRole('button', { name: '전체 15개 보기', exact: true }).click()
  await expect(dialog.getByRole('heading', { name: '테마와 추가 문제', exact: true })).toBeFocused()
  await expect(dialog.locator('[data-daily-problem-index]')).toHaveCount(0)
  await dialog.getByRole('button', { name: '창 닫기', exact: true }).focus()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.locator('[data-daily-group]:enabled').last()).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: '창 닫기', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(summary.getByRole('button', { name: '전체 15개 보기', exact: true })).toBeFocused()
  const fullReport = page.getByRole('button', { name: '리포트 전체 보기', exact: true })
  await expect(page.locator('.report-toolbar')).not.toContainText('이 결과 오류 신고')
  await fullReport.click()
  await expect(dialog.locator('.daily-navigation-heading')).toHaveText('테마와 추가 문제')
  await expect(dialog.locator('[data-daily-group]:enabled')).toHaveCount(2)
  await expect(dialog.locator('[data-daily-story]')).toHaveCount(11)
  await expect(dialog.locator('[data-daily-story]:disabled')).toHaveCount(10)
  await expect(dialog.getByRole('button', { name: '소리 탐정 0개', exact: true })).toBeDisabled()
  await page.screenshot({ path: info.outputPath('daily-report-root.png') })
  await dialog.locator('[data-daily-group]:enabled').first().click()
  await expect(dialog.locator('[data-daily-problem-link]')).toHaveCount(5)
  await page.screenshot({ path: info.outputPath('daily-report-problems.png') })
  await dialog.locator('[data-daily-problem-link="0"]').click()
  await expect(dialog.locator('[data-daily-problem-index="0"]')).toBeVisible()
  await expect(dialog.getByRole('navigation', { name: '문제 탐색 경로' })).toHaveText('전체 리포트잃어버린 것 찾기상세 기록')
  await page.keyboard.press('Escape')
  await expect(fullReport).toBeFocused()
})

test('difficulty numbers open only matching activities, including missing difficulty @responsive', async ({ page }) => {
  const summary = await openDaily(page, 'missing')
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  for (const choice of [
    { label: '쉬웠어요', indices: [3, 4, 5, 6, 7] },
    { label: '보통', indices: [8, 9, 10, 11, 12, 13] },
    { label: '어려웠어요', indices: [14] },
    { label: '기록 없음', indices: [0, 1, 2] },
  ]) {
    const count = summary.getByRole('button', { name: `${choice.label} ${choice.indices.length}개 활동 보기`, exact: true })
    await count.click()
    await expect(dialog.locator('.daily-report-filter')).toContainText(`${choice.label} · ${choice.indices.length}개 활동`)
    await expect(dialog.locator(`[data-daily-problem-index="${choice.indices[0]}"]`)).toBeVisible()
    await expect(dialog.locator('.daily-navigation-heading')).toBeFocused()
    const matching = dialog.getByRole('navigation', { name: '선택한 조건의 활동 이동' })
    if (choice.indices.length > 1) {
      for (const index of choice.indices.slice(1)) {
        await matching.getByRole('button', { name: '다음 활동' }).click()
        await expect(dialog.locator(`[data-daily-problem-index="${index}"]`)).toBeVisible()
      }
      await expect(matching.getByRole('button', { name: '다음 활동' })).toBeDisabled()
    } else {
      await expect(matching).toHaveCount(0)
    }
    await dialog.getByRole('button', { name: '전체 리포트', exact: true }).click()
    const found: number[] = []
    const groupCount = await dialog.locator('[data-daily-group]:enabled').count()
    for (let n = 0; n < groupCount; n++) {
      await dialog.locator('[data-daily-group]:enabled').nth(n).click()
      found.push(...await dialog.locator('[data-daily-problem-link]').evaluateAll(els => els.map(e => Number(e.getAttribute('data-daily-problem-link')))))
      await dialog.getByRole('button', { name: '전체 리포트', exact: true }).click()
    }
    expect(found.sort((a,b) => a-b)).toEqual(choice.indices)
    await page.keyboard.press('Escape')
    await expect(count).toBeFocused()
  }
})

test('private daily summary keeps numeric records and labels hidden follow-up counts @responsive', async ({ page }) => {
  const summary = await openDaily(page, 'private')
  await expect(summary.getByRole('region', { name: '되묻기가 있었던 활동', exact: true })).toContainText('원문 비공개')
  await expect(summary.getByRole('region', { name: '되묻기에 대한 답변 기록', exact: true })).not.toContainText('0개')
  await expect(summary.getByRole('region', { name: '돌아보기를 작성한 활동', exact: true })).toContainText('15개')
  await expect(summary.locator('.daily-difficulty-legend')).toContainText('쉬웠어요8개')
  await expect(summary.getByRole('region', { name: '되묻기가 있었던 활동', exact: true }).getByRole('button')).toHaveCount(0)
  await expect(summary.getByRole('button', { name: '기록 없음 0개 활동 보기', exact: true })).toHaveCount(0)
  await summary.getByRole('button', { name: '쉬웠어요 8개 활동 보기', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  await expect(dialog.locator('[data-daily-problem-index]')).toHaveCount(1)
  await expect(dialog.locator('[data-daily-problem-index="0"]')).toBeVisible()
  await expect(dialog.locator('.report-final-answer')).toContainText('아이가 답변 원문을 비공개로 두었어요.')
  await expect(dialog.locator('.report-final-answer blockquote')).toHaveCount(0)
  await expect(dialog).not.toContainText('서로의 의견을 듣고 근거를 비교해요.')
  await expect(dialog.getByRole('button', { name: '내용', exact: true })).toHaveCount(0)
})

test('empty daily summary has an honest empty state without an invented chart @responsive', async ({ page }) => {
  const summary = await openDaily(page, 'empty')
  await expect(summary).toContainText('이날은 완료한 활동이 없어요.')
  await expect(summary.locator('.daily-donut')).toHaveCount(0)
  await expect(summary.getByRole('region', { name: '오늘 완료한 활동', exact: true })).toContainText('0개')
  await expect(summary.getByRole('button')).toHaveCount(0)
  await page.getByRole('button', { name: '리포트 전체 보기', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true })
  await expect(dialog).toContainText('이날은 기록이 없습니다.')
  await expect(dialog.locator('[data-daily-group]')).toHaveCount(11)
  await expect(dialog.locator('[data-daily-group]:disabled')).toHaveCount(11)
  await expect(dialog.locator('.daily-navigation-count')).toHaveText(Array(11).fill('0개'))
})
