import { expect, test } from '@playwright/test'
import { openCompletedReport } from './support/reports.ts'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { subscribePremium } from './support/payment.ts'
import { loginStudent, solveNarrative, startExtraMission } from './support/student.ts'
import { queueReport } from './support/db.ts'
import { allowParentOriginals, studentIdOf } from './support/memoryBook.ts'
import { ensureExplanationModel } from './support/admin.ts'

// 대표 답변 설명(FN-RPT-09)은 프리미엄·답변 공개·초5~6 서술 답변의 M2 점수가 모두 있어야 생성된다.
// M2는 scoring-stub, 설명 sLLM은 llm-stub(compose.e2e.yaml), 11번 기준표 핵심어는 seed/learning.sql,
// 설명 모델 활성 범위는 관리자 모델 레지스트리 등록·활성화(ensureExplanationModel)
const mission = '따뜻해진 컵의 비밀' // demo_missions.sql 11번 (초5·ANALYZE·NARRATIVE)


test('프리미엄 학생 서술 답·되묻기 → 일일 리포트 문제 기록 → 주간 리포트 대표 답변 설명', async ({ browser, context, page, baseURL }) => {
  await ensureExplanationModel(browser, baseURL!)
  const nickname = `리포트${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('reports'))
  await onboardParent(page, nickname, { grade: 5 })
  await subscribePremium(page)
  allowParentOriginals(studentIdOf(nickname)) // 임시: core #1061 전 서버는 기본 비공개

  const student = await loginStudent(browser, page, nickname, '리포트 E2E')
  try {
    await startExtraMission(student.page, mission)
    await solveNarrative(student.page, '따뜻한 물을 부으면 열이 컵으로 옮겨 가서 컵도 따뜻해져요. 손으로 만지면 온도가 올라간 것을 느낄 수 있어요.', {
      followup: '뜨거운 물의 열이 컵 벽을 지나 바깥까지 전해지기 때문이에요.',
    })
  } finally {
    await student.context.close()
  }

  const [day] = queueReport(nickname, { periodType: 'DAILY' }).split(' ')
  // 프리미엄(E2E-PLUS reportNarrative=true) 주간이라 ReportJobService가 계산하는 narrativeEnabled와 같다
  const [from, to] = queueReport(nickname, { narrative: true }).split(' ')

  await page.getByRole('link', { name: '리포트·기록에 물어보기', exact: true }).click()
  await page.waitForURL('**/parent/report**')
  await openCompletedReport(page, '일일', day)
  await expect(page.getByRole('heading', { name: '일일 리포트', exact: true })).toBeVisible()
  await page.getByRole('region', { name: '오늘 푼 활동', exact: true }).getByRole('button', { name: /^전체 \d+개 보기$/ }).click()
  await expect(page.getByRole('heading', { name: '일일 리포트 전체 보기' })).toBeVisible()
  await expect(page.locator('[data-daily-group]:enabled').first()).toBeVisible()
  const groups = await page.locator('[data-daily-group]:enabled').count()
  for (let i = 0; i < groups; i++) {
    await page.locator('[data-daily-group]:enabled').nth(i).click()
    const link = page.locator('[data-daily-problem-link]').filter({ hasText: mission })
    if (await link.count()) { await link.first().click(); break }
    await page.getByRole('button', { name: '전체 리포트', exact: true }).click()
  }
  const problem = page.locator('article.report-answer-comparison')
  await expect(problem.getByText('되묻기 1', { exact: true })).toBeVisible()
  await expect(problem.locator('.report-followup').filter({ has: page.getByText('되묻기 1', { exact: true }) }).getByText('그렇게 생각한 까닭을 한 가지 더 이야기해 줄래요?', { exact: true })).toBeVisible()
  await expect(problem.getByRole('heading', { name: '마지막 답' })).toBeVisible()
  await expect(problem.getByRole('button', { name: '내용', exact: true })).toBeVisible()
  await page.getByRole('dialog', { name: '일일 리포트 전체 보기', exact: true }).getByRole('button', { name: '창 닫기', exact: true }).click()

  await openCompletedReport(page, '주간', `${from} ~ ${to}`)
  await expect(page.getByRole('heading', { name: '주간 리포트', exact: true })).toBeVisible()
  await page.getByRole('navigation', { name: '주간 기록 바로가기' }).getByRole('button', { name: /^대표 답변 설명 / }).click()
  await page.getByRole('list', { name: '대표 답변 설명 활동 목록' }).getByRole('button').filter({ hasText: mission }).click()
  const explanations = page.getByRole('region', { name: '대표 답변 설명' })
  await expect(page.getByRole('dialog').locator('.report-reader-heading')).toContainText(mission)
  await expect(explanations.getByRole('heading', { name: '상세 분석', exact: true })).toBeVisible()
  await expect(explanations.getByRole('note')).toHaveCount(0)
})
