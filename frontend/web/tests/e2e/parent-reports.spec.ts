import { expect, test } from '@playwright/test'
import { openCompletedReport } from './support/reports.ts'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { subscribePremium } from './support/payment.ts'
import { loginStudent, solveNarrative, startExtraMission } from './support/student.ts'
import { queueReport } from './support/db.ts'
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

  await page.getByRole('link', { name: '리포트·AI 챗봇', exact: true }).click()
  await page.waitForURL('**/parent/report**')
  await openCompletedReport(page, '일일', day)
  await expect(page.getByRole('heading', { name: '일일 리포트', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '그날 푼 문제' })).toBeVisible()
  const problem = page.locator('details.report-answer-comparison', { has: page.locator('summary').getByText(mission, { exact: true }) })
  await problem.locator('summary').click()
  await expect(problem.getByText('되묻기 1', { exact: true })).toBeVisible()
  await expect(problem.locator('.report-followup').filter({ has: page.getByText('되묻기 1', { exact: true }) }).getByText('그렇게 생각한 까닭을 한 가지 더 이야기해 줄래요?', { exact: true })).toBeVisible()
  await expect(problem.getByRole('heading', { name: '마지막 답' })).toBeVisible()
  await expect(problem.getByRole('button', { name: '내용', exact: true })).toBeVisible()

  await openCompletedReport(page, '주간', `${from} ~ ${to}`)
  await expect(page.getByRole('heading', { name: '주간 리포트', exact: true })).toBeVisible()
  const explanations = page.getByRole('region', { name: '대표 답변 설명' })
  await expect(page.locator('.weekly-activity-heading')).toContainText(mission)
  await expect(explanations.getByRole('heading', { name: '상세 분석', exact: true })).toBeVisible()
  await expect(explanations.getByRole('note')).toHaveCount(0)
})
