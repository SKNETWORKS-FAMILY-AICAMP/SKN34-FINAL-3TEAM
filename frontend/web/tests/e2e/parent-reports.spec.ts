import { expect, test, type Page } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { subscribePremium } from './support/payment.ts'
import { loginStudent, solveNarrative, startExtraMission, studentMenu } from './support/student.ts'
import { queueReport } from './support/db.ts'
import { ensureExplanationModel } from './support/admin.ts'

// 대표 답변 설명(FN-RPT-09)은 프리미엄·답변 공개·초5~6 서술 답변의 M2 점수가 모두 있어야 생성된다.
// M2는 scoring-stub, 설명 sLLM은 llm-stub(compose.e2e.yaml), 11번 기준표 핵심어는 seed/learning.sql,
// 설명 모델 활성 범위는 관리자 모델 레지스트리 등록·활성화(ensureExplanationModel)
const mission = '따뜻해진 컵의 비밀' // demo_missions.sql 11번 (초5·ANALYZE·NARRATIVE)

async function openReport(page: Page, kind: '일일 리포트' | '주간 리포트', heading: string) {
  if (await page.getByRole('dialog').count()) await page.getByRole('dialog').getByRole('button', { name: /닫기$/ }).first().click()
  await page.getByRole('link', { name: '리포트·AI 챗봇', exact: true }).click()
  await page.waitForURL('**/parent/report**')
  const card = page.locator('.parent-report-group').filter({ has: page.getByRole('heading', { name: kind, exact: true }) }).locator('article').filter({ has: page.getByRole('heading', { name: heading, exact: true }) })
  await expect(async () => {
    await page.reload()
    await page.getByRole('button', { name: '리포트 자세히 보기', exact: false }).click()
    await expect(card.getByText('생성 완료')).toBeVisible({ timeout: 5_000 })
  }).toPass({ timeout: 180_000, intervals: [3_000] })
  await card.getByRole('button', { name: '자세히 보기' }).click()
}

test('프리미엄 학생 서술 답·되묻기 → 일일 리포트 문제 기록 → 주간 리포트 대표 답변 설명', async ({ browser, context, page, baseURL }) => {
  await ensureExplanationModel(browser, baseURL!)
  const nickname = `리포트${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('reports'))
  await onboardParent(page, nickname, { grade: 5 })
  await subscribePremium(page)

  const student = await loginStudent(browser, page, nickname, '리포트 E2E')
  try {
    // 설명·원문은 학생이 학부모 공개를 켠 답변만(P13)
    await studentMenu(student.page, '설정')
    await student.page.getByRole('radio', { name: '학부모님께 공개할게요' }).click()
    await expect(student.page.getByRole('status').filter({ hasText: '지금은 공개예요.' })).toBeVisible()
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

  await openReport(page, '일일 리포트', day)
  await expect(page.getByRole('heading', { name: '일일 리포트', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '활동 기록', exact: true }).click()
  await expect(page.getByRole('heading', { name: '그날 푼 문제' })).toBeVisible()
  const problem = page.locator('details.report-answer-comparison', { has: page.locator('summary').getByText(mission, { exact: true }) })
  await problem.locator('summary').click()
  await expect(problem.getByText('되묻기 1', { exact: true })).toBeVisible()
  await expect(problem.locator('.report-followup').filter({ has: page.getByText('되묻기 1', { exact: true }) }).getByText('그렇게 생각한 까닭을 한 가지 더 이야기해 줄래요?', { exact: true })).toBeVisible()
  await expect(problem.getByRole('heading', { name: '마지막 답' })).toBeVisible()
  await expect(problem.getByRole('button', { name: '원문 근거' })).toBeVisible()

  await openReport(page, '주간 리포트', `${from} ~ ${to}`)
  await expect(page.getByRole('heading', { name: '주간 리포트', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '설명과 근거', exact: true }).click()
  const explanations = page.getByRole('region', { name: '대표 답변 설명' })
  const card = explanations.locator('article', { has: page.getByRole('heading', { name: mission, exact: true }) })
  await expect(card.getByText('AI 관찰', { exact: true })).toBeVisible()
  await expect(explanations.getByRole('note')).toHaveCount(0)
})
