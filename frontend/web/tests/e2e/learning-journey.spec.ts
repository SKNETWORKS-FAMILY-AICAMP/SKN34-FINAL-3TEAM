import { expect, test, type BrowserContext } from '@playwright/test'
import { newParent, useGoogleIdentity, type GoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { queueWeeklyReport } from './support/db.ts'
import { expectJournalDone, loginStudent, solveNarrative, startExtraMission, studentMenu } from './support/student.ts'

const mission = '쉬는 시간을 늘린다면?' // backend/learning-service/db/seed/demo_missions.sql 2번 (초3·NARRATIVE)

test.describe.serial('학생 미션 → 학부모 대시보드·리포트', () => {
  let parent: GoogleIdentity, nickname: string, studentContext: BrowserContext | undefined
  test.afterEach(async () => { await studentContext?.close(); studentContext = undefined })
  test.beforeAll(() => {
    parent = newParent('journey')
    nickname = `학생${Date.now().toString(36)}`
  })

  // 학생 토큰은 메모리에만 있으므로 학생 단계에서는 page.goto·새로고침 없이 화면 안에서만 이동한다.
  test('학생 미션 제출 → 피드백 → 돌아보기 완료 → 답 공개',async ({ context, page: parentPage, browser }) => {
    await useGoogleIdentity(context, parent)
    await onboardParent(parentPage, nickname)
    // #548: students enter through a registered device and PIN, not a parent-page button.
    const student = await loginStudent(browser, parentPage, nickname, '학습 여정 E2E')
    studentContext = student.context
    const page = student.page

    // 미션 고르기는 추가 문제(EXTRA)라 무료는 프리미엄 전용이지만, E2E 무료 상품은 시드에서 명시적으로 켰다(seed/core.sql, #506)
    await startExtraMission(page, mission)
    await solveNarrative(page, '저는 찬성이에요. 쉬는 시간이 길면 친구들과 더 오래 놀 수 있기 때문이에요.')
    // #648: 완료 기록은 내 공책 한 줄의 '마무리' 상태로 확인한다(옛 기록 카드 "국어 · 제목 … 완료" 대신)
    await expectJournalDone(page, mission)

    // 답변 원문은 기본 비공개라 학부모 공책에 보이도록 학생이 공개로 바꾼다.
    await studentMenu(page, '설정')
    await page.getByRole('radio', { name: '학부모님께 공개할게요' }).click()
    await expect(page.getByRole('status').filter({ hasText: '지금은 공개예요.' })).toBeVisible()
  })

  // 학생 기기와 별개인 새 보호자 컨텍스트에서 로그인해 공개한 기록을 확인한다.
  test('학부모 대시보드 → 주간 리포트', async ({ context, page }) => {
    await useGoogleIdentity(context, parent)
    await page.goto('/login')
    await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
    await page.waitForURL('**/parent/journal**')
    await expect(page.getByRole('heading', { name: `${nickname}의 학습 현황`, exact: true })).toBeVisible()
    await page.getByRole('button', { name: '생각 활동 전체 보기', exact: true }).click()
    const row=page.getByRole('row').filter({hasText:mission})
    await expect(row.getByRole('button',{name:'원문 보기 ↗'})).toBeVisible()
    await page.getByRole('dialog').getByRole('button',{name:/닫기$/}).click()

    const [from, to] = queueWeeklyReport(nickname).split(' ')
    await page.getByRole('link', { name: '리포트·AI 챗봇', exact: true }).click()
    await page.waitForURL('**/parent/report**')
    const card = page.locator('article', { has: page.getByRole('heading', { name: `${from} ~ ${to}` }) })
    await expect(async () => {
      await page.reload()
      await page.getByRole('button',{name:'리포트 자세히 보기',exact:false}).click()
      await expect(card.getByText('생성 완료')).toBeVisible({ timeout: 5_000 })
    }).toPass({ timeout: 120_000, intervals: [3_000] })

    await card.getByRole('button', { name: '자세히 보기' }).click()
    await expect(page.getByRole('heading', { name: '주간 리포트', exact:true })).toBeVisible()
    await expect(page.getByText(`${from} ~ ${to}`, { exact: false })).toBeVisible()
    await expect(page.getByText('수치 리포트입니다. 이 자녀의 플랜에는 서술 요약이 포함되지 않습니다.')).toBeVisible()
  })
})
