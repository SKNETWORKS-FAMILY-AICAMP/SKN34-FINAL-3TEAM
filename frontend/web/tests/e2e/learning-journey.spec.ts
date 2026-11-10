import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity, type GoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { queueWeeklyReport } from './support/db.ts'

const mission = '쉬는 시간을 늘린다면?' // backend/learning-service/db/seed/demo_missions.sql 2번 (초3·NARRATIVE)

test.describe.serial('학생 미션 → 학부모 대시보드·리포트', () => {
  let parent: GoogleIdentity, nickname: string
  test.beforeAll(() => {
    parent = newParent('journey')
    nickname = `학생${Date.now().toString(36)}`
  })

  // 학생 토큰은 메모리에만 있으므로 학생 단계에서는 page.goto·새로고침 없이 화면 안에서만 이동한다.
  test('학생 미션 제출 → 피드백 → 돌아보기 완료 → 답 공개',async ({ context, page }) => {
    await useGoogleIdentity(context, parent)
    await onboardParent(page, nickname)
    await page.getByRole('button', { name: '이 자녀로 학습 시작' }).click()
    await page.waitForURL('**/student/home**')

    await page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '미션 고르기' }).click()
    await page.locator('article', { has: page.getByRole('heading', { name: mission }) })
      .getByRole('button', { name: '미션 열기' }).click()
    await page.getByRole('button', { name: '작성하기 · 진행 중이면 이어서' }).click()
    await page.waitForURL('**/student/attempts/**')

    await page.getByLabel('내 생각과 까닭').fill('저는 찬성이에요. 쉬는 시간이 길면 친구들과 더 오래 놀 수 있기 때문이에요.')
    await page.getByRole('button', { name: '다 썼어요' }).click()
    // llm-stub이 모든 요소를 답변 원문 인용으로 돌려주므로 정답 판정
    await expect(page.getByText('정답을 확인했어요.')).toBeVisible({ timeout: 60_000 })

    await page.getByRole('button', { name: '이대로 돌아보기' }).click()
    await expect(page.getByRole('heading', { name: /(정답|예시 답)과 비교해 보세요\./ })).toBeVisible()
    await expect(page.getByRole('list', { name: '마무리 체크리스트' })).toBeVisible()

    await page.getByRole('button', { name: '돌아보기 남기기' }).click()
    await page.getByRole('button', { name: '보통이에요' }).click()
    await page.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
    const record = page.locator('article', { hasText: `국어 · ${mission}` })
    await expect(record).toBeVisible()
    await expect(record.getByText('완료', { exact: false })).toBeVisible()

    // 답변 원문은 기본 비공개라 학부모 공책에 보이도록 학생이 공개로 바꾼다.
    await page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '공개 설정', exact: true }).click()
    await page.getByRole('radio', { name: '학부모님께 공개할게요' }).click()
    await expect(page.getByRole('status').filter({ hasText: '현재 공개 상태입니다.' })).toBeVisible()
  })

  // 학생 모드 진입 시 학부모 세션이 잠기므로(보호자 비밀번호 미설정) 새 컨텍스트에서 다시 로그인한다.
  test('학부모 대시보드 → 주간 리포트', async ({ context, page }) => {
    await useGoogleIdentity(context, parent)
    await page.goto('/login')
    await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
    await page.waitForURL('**/parent/journal**')
    await expect(page.getByRole('heading', { name: `${nickname}의 학습 현황`, exact: true })).toBeVisible()
    const row = page.getByRole('row', { name: new RegExp(mission.replace('?', '\\?')) })
    await expect(row.getByText('완료', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: `${mission} 원문 보기` })).toBeVisible()

    const [from, to] = queueWeeklyReport(nickname).split(' ')
    await page.getByRole('link', { name: '리포트', exact: true }).click()
    await page.waitForURL('**/parent/report**')
    const card = page.locator('article', { has: page.getByRole('heading', { name: `${from} ~ ${to}` }) })
    await expect(async () => {
      await page.reload()
      await expect(card.getByText('생성 완료')).toBeVisible({ timeout: 5_000 })
    }).toPass({ timeout: 120_000, intervals: [3_000] })

    await card.getByRole('button', { name: '리포트 상세 보기' }).click()
    await expect(page.getByRole('heading', { name: '리포트 상세' })).toBeVisible()
    await expect(page.getByText(`실제 리포트 기간 · ${from} ~ ${to}`, { exact: false })).toBeVisible()
    await expect(page.getByText('수치 리포트입니다. 이 자녀의 플랜에는 서술 요약이 포함되지 않습니다.')).toBeVisible()
  })
})
