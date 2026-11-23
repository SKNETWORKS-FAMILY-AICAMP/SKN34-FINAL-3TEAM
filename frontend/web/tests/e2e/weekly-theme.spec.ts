import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { expectJournalDone, loginStudent, solveNarrative, studentMenu, throughTodayScene } from './support/student.ts'
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
  const monday = kstWeekday() === 1
  try {
    // #648·#487 새 홈: 옛 "이번 주 테마" 카드·요일별 문제 목록 대신 왼쪽 테마 제목·오늘 문제 버튼, 오른쪽 요일 칩(FN-RET-07, user-flow 3.2)
    await expect(page.getByRole('heading', { level: 1, name: theme.title, exact: true })).toBeVisible()
    await expect(page.getByText(`안녕, ${nickname}! · 이번 주 테마`)).toBeVisible()
    const chips = page.getByRole('list', { name: '이번 주 진행' })
    const mondayChip = chips.getByRole('listitem', { name: /^월요일 / })
    // 안 푼 문제를 풀 수 있는 마지막 날: 평일은 토요일, 토요일(프리미엄 일요일)은 오늘(#487 45행)
    const until = kstWeekday() === 6 ? '오늘까지' : '토요일까지'
    await expect(mondayChip).toHaveAccessibleName(monday ? '월요일 오늘 문제' : `월요일 아직 안 풀었어요, ${until} 풀 수 있어요`)
    // 월요일 문제를 여는 버튼: 월요일에는 "오늘 문제 풀기", 화~토에는 "아직 안 푼 문제 N개 · 월…요일"(가장 앞 요일인 월요일부터 엶,
    // 다른 요일은 요일 칩으로 고름 #487 42행)
    const openMonday = monday
      ? page.getByRole('button', { name: '오늘 문제 풀기', exact: true })
      : page.getByRole('button', { name: /^아직 안 푼 문제 \d개 · 월/ })
    await openMonday.click()

    // 그 주 처음 문제를 열면 시작 이야기부터(/student/theme/intro, #440 사용자 결정 2026-11-13·14). 옛 홈 카드의 시작 이야기 글은 여기로 옮겨 왔다
    await page.waitForURL('**/student/theme/intro')
    await expect(page.getByRole('heading', { level: 1, name: theme.title, exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: '시작 이야기' }).getByText(THEME_INTRO)).toBeVisible()
    await page.getByRole('button', { name: /이번 주 시작하기 · 오늘 문제로/ }).click()
    // 시작 이야기를 닫으면 누른 그 문제로 이어진다: 오늘 장면(대화가 있으면)을 지나 답변 작성(미션 안내 없음, #807)
    await throughTodayScene(page)
    await expect(page.getByRole('heading', { level: 1, name: MONDAY_MISSION })).toBeVisible()

    await solveNarrative(page, '저는 반대예요. 쉬는 시간이 길어지면 수업이 늦게 끝나서 집에 늦게 가기 때문이에요.', {
      followup: '그리고 쉬는 시간이 길면 다음 수업에 집중하기까지 시간이 더 걸릴 것 같아요.',
    })
    await expectJournalDone(page, MONDAY_MISSION)

    // 홈으로 돌아오면 그 요일이 끝난 상태: 옛 "끝냈어요" 표시 대신 요일 칩 ✓(월요일에 풀면 "그날 풀었어요", 늦게 풀면 "풀었어요, 그날은 아니에요")
    await studentMenu(page, '홈')
    await expect(mondayChip).toHaveAccessibleName(monday ? '월요일 그날 풀었어요' : '월요일 풀었어요, 그날은 아니에요')
    await expect(openMonday).toHaveCount(0)

    // 포인트: 돌아보기 저장 때 미션 학습 완료 10(V35). 당일 풀이 5는 월요일에만 더해진다(V43)
    // #648: 잔액·내역은 설정 카드의 "내 포인트 보기"(/student/points)
    await studentMenu(page, '설정')
    await page.getByRole('button', { name: /내 포인트 보기/ }).click()
    const balance = page.locator('.st-balance')
    await expect(balance).toHaveText(/지금 \d+포인트/)
    // 포인트는 완료 뒤 서비스 사이 메시지로 쌓여, 화면을 연 순간엔 아직 0이거나 일부만 왔을 수 있다. 한 번만 읽지 말고
    // 새 학생이 받을 몫(학습 완료 10 + 월요일이면 당일 풀이 5)이 다 찰 때까지 기다린다.
    // (#807 마무리가 짧아져 포인트 화면에 더 빨리 오면서 드러남: 새 DB 전체 실행에서 0을 읽고 실패, 실패 화면엔 15)
    const points = async () => Number((await balance.locator('strong').textContent()) ?? 0)
    await expect.poll(points, { timeout: 15_000 }).toBe(monday ? 15 : 10)
    const before = await points()
    await expect(page.locator('.st-ledger').getByText('미션 학습 완료')).toBeVisible()

    // 꾸미기: 시드 아이템(E2E 모자, 10포인트) 해금 → 착용
    // #648: 꾸미기는 대화상자가 아니라 페이지(/student/customize). 모자는 "옷 입히기" 탭, 카드를 눌러 미리 보고 아래 버튼으로 해금·입기
    await page.getByRole('button', { name: '꾸미기 해금하러 가기' }).click()
    await page.waitForURL('**/student/customize**')
    await page.getByRole('tab', { name: '옷 입히기' }).click()
    const hat = page.getByRole('group', { name: '모자', exact: true }).getByRole('button', { name: /^E2E 모자/ })
    await expect(hat).toContainText('10포인트')
    await hat.click()
    await expect(hat).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('button', { name: 'E2E 모자 10포인트로 열기' }).click()
    await page.getByRole('region', { name: '꾸미기 해금 확인' }).getByRole('button', { name: '포인트로 해금하기' }).click()
    await expect(page.getByText('해금했어요! 이제 골라서 쓸 수 있어요.')).toBeVisible()
    await expect(page.getByText(`내 포인트 ${before - 10}`, { exact: true })).toBeVisible()
    await expect(hat).toContainText('가지고 있어요')
    await expect(hat).toBeEnabled()
    await page.getByRole('button', { name: '이대로 입기', exact: true }).click()
    await expect(page.getByText('골랐어요!', { exact: true })).toBeVisible()
    // 옛 라디오 checked 대신: 고른 카드가 눌린 상태이고 아래 버튼이 "입고 있어요"(지금 입은 것과 같음)
    await expect(hat).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: '입고 있어요', exact: true })).toBeDisabled()

    // 옛 '다 골랐어요'로 닫던 대화상자 대신 설정 → 내 포인트에서 잔액·차감 내역 확인
    await studentMenu(page, '설정')
    await page.getByRole('button', { name: /내 포인트 보기/ }).click()
    await expect(balance).toHaveText(`지금 ${before - 10}포인트`)
    await expect(page.locator('.st-ledger li').filter({ has: page.getByText('-10', { exact: true }) })).toHaveCount(1)
  } finally {
    await studentContext.close()
  }
})
