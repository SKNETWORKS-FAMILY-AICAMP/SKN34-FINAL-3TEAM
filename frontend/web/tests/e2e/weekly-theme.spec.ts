import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, solveNarrative, studentMenu } from './support/student.ts'
import { ensureWeeklyTheme, kstWeekday, MONDAY_MISSION, THEME_INTRO } from './support/theme.ts'

// 서버 날짜를 고정할 수 없어(learning ClockConfig = 시스템 KST) 무료 일요일 THEME_DAY_CLOSED(FN-RET-07)인 날은 건너뛴다.
// 월요일 문제는 월~토 열려 있으므로 나머지 요일에는 같은 흐름이 된다.
test.skip(kstWeekday() === 0, 'KST 일요일: 무료 이용권은 주간 테마 문제가 닫힘(THEME_DAY_CLOSED)')

test('주간 테마 시작 이야기 → 월요일 문제·되묻기 → 마무리 → 포인트 적립 → 꾸미기 해금·착용', async ({ browser, context, page: parentPage, baseURL }) => {
  const theme = await ensureWeeklyTheme(browser, baseURL!)
  const nickname = `테마${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('theme'))
  await onboardParent(parentPage, nickname)
  const { context: studentContext, page } = await loginStudent(browser, parentPage, nickname, '주간 테마 E2E')
  try {
    // 홈 "이번 주 테마" 카드: 제목·시작 이야기(FN-RET-07, user-flow 3.2)
    const card = page.locator('section', { has: page.getByRole('heading', { name: theme.title, exact: true }) })
    await expect(card.getByText('이번 주 테마')).toBeVisible()
    await expect(card.getByText(THEME_INTRO)).toBeVisible()
    const monday = card.getByRole('list', { name: '요일별 문제' }).getByRole('listitem').filter({ hasText: MONDAY_MISSION })
    await monday.getByRole('button', { name: '오늘 문제 풀기' }).click()
    await page.getByRole('button', { name: '미션 시작하기' }).click()
    await page.waitForURL('**/student/attempts/**')

    await solveNarrative(page, '저는 반대예요. 쉬는 시간이 길어지면 수업이 늦게 끝나서 집에 늦게 가기 때문이에요.', {
      followup: '그리고 쉬는 시간이 길면 다음 수업에 집중하기까지 시간이 더 걸릴 것 같아요.',
    })
    await expect(page.locator('article', { hasText: `국어 · ${MONDAY_MISSION}` }).getByText('완료', { exact: false })).toBeVisible()

    // 홈으로 돌아오면 그 요일이 끝난 상태
    await studentMenu(page, '생각 지도')
    await expect(monday.getByText('끝냈어요', { exact: false })).toBeVisible()
    await expect(monday.getByRole('button', { name: '오늘 문제 풀기' })).toHaveCount(0)

    // 포인트: 돌아보기 저장 때 미션 학습 완료 10(V35). 당일 풀이 5는 월요일에만 더해진다(V43)
    await studentMenu(page, '설정')
    const balance = page.locator('.st-balance')
    await expect(balance).toHaveText(/지금 \d+포인트/)
    const before = Number((await balance.locator('strong').textContent()) ?? 0)
    expect(before).toBeGreaterThanOrEqual(10)
    await expect(page.locator('.st-ledger').getByText('미션 학습 완료')).toBeVisible()

    // 꾸미기: 시드 아이템(E2E 모자, 10포인트) 해금 → 착용
    await page.getByRole('button', { name: '꾸미기 해금하러 가기' }).click()
    const dialog = page.getByRole('dialog', { name: '내 생각 지도 꾸미기' })
    await dialog.getByRole('button', { name: 'E2E 모자 해금하기' }).click()
    await dialog.getByRole('region', { name: '꾸미기 해금 확인' }).getByRole('button', { name: '포인트로 해금하기' }).click()
    await expect(dialog.getByText('해금했어요! 이제 골라서 쓸 수 있어요.')).toBeVisible()
    await expect(dialog.getByText(`내 포인트 ${before - 10}`)).toBeVisible()
    const hat = dialog.getByRole('radio', { name: 'E2E 모자' })
    await expect(hat).toBeEnabled()
    await hat.check()
    await expect(dialog.getByText('골랐어요!')).toBeVisible()
    await expect(hat).toBeChecked()
    await dialog.getByRole('button', { name: '다 골랐어요' }).click()
    await expect(balance).toHaveText(`지금 ${before - 10}포인트`)
    await expect(page.locator('.st-ledger li').filter({ hasText: '-10' })).toHaveCount(1)
  } finally {
    await studentContext.close()
  }
})
