import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, studentMenu } from './support/student.ts'

// 내 방 → 추억 앨범(FN-RET-09·11). 앨범은 지난주에 다섯 문제를 모두 끝낸 회차만 보여 주므로 새 학생은 빈 앨범이다.
// 지난 회차가 있는 앨범·회차 상세는 지난주 기록 준비 방식(#624)이 정해진 뒤 추가한다.
test('내 방 진입 → 추억 앨범(빈 상태) → 내 방으로', async ({ browser, context, page: parentPage }) => {
  const nickname = `방${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('room'))
  await onboardParent(parentPage, nickname)
  const { context: studentContext, page } = await loginStudent(browser, parentPage, nickname, '내 방 E2E')
  try {
    // #648 내 방은 "○○의 미니룸" 제목 + 가구 이름표 6개(가구 = 메뉴, 사용자 결정 2026-11-16).
    // 옛 이름표 '추억의 벽'·'학습 책상'·'옷장'은 '추억의 벽 · 액자'·'책상 · 오늘 문제'·'옷장 · 옷 갈아입기'가 되었고 나머지 셋을 더 본다
    const room = page.getByRole('heading', { name: `${nickname}의 미니룸`, exact: true })
    await studentMenu(page, '내 방')
    await expect(room).toBeVisible()
    for (const spot of ['추억의 벽 · 액자', '책상 · 오늘 문제', '옷장 · 옷 갈아입기', '창문 · 이번 주 이야기', '문 · 친구 생각', '책장 · 내 공책'])
      await expect(page.getByRole('button', { name: spot, exact: true })).toBeVisible()

    // #705 방 꾸미기 서랍(실서버 core #723·#736): 바닥·방 소품 탭이 있고, 놓은 칸 목록(decor-spots)을 읽어 새 학생은 놓음 0/0.
    // 포인트가 없는 새 학생이라 사기·놓기·저장은 목업 브라우저 시험(roomDecor.spec)이 맡는다
    await page.getByRole('button', { name: '방 꾸미기', exact: true }).click()
    const drawer = page.getByRole('region', { name: '방 꾸미기' })
    await drawer.getByRole('button', { name: '방 소품', exact: true }).click()
    await expect(drawer.locator('.st-decor-card').first()).toContainText('놓음 0/0')
    await expect(drawer.getByRole('alert')).toHaveCount(0)
    await page.getByRole('button', { name: '취소', exact: true }).click()

    await page.getByRole('button', { name: '추억 앨범 열기' }).click()
    await expect(page.getByRole('heading', { name: '추억 앨범', exact: true })).toBeVisible()
    // #648 앨범은 빈 상태에도 액자 목록 칸을 두고 그 안에 안내 한 칸을 넣는다(옛 region '빈 앨범 안내' + 목록 없음 대신).
    // 안내 칸은 이번 주 게시 테마가 없으면 '빈 앨범 안내', 있으면 '이번 주 액자 자리'(weekly-theme 뒤 같은 스택에서 다시 돌 때)
    const frames = page.getByRole('list', { name: '보유한 기념 액자' })
    await expect(page.getByText('기념 액자 0개', { exact: true })).toBeVisible()
    await expect(frames.getByRole('listitem', { name: /^(빈 앨범 안내|이번 주 액자 자리)$/ })).toBeVisible()
    await expect(frames.getByRole('button')).toHaveCount(0)

    // 앨범에서 돌아가는 버튼은 "← 내 방"(학생 메뉴의 '내 방'과 구분해 앨범 메뉴 안에서 찾는다)
    await page.getByRole('navigation', { name: '앨범 메뉴' }).getByRole('button', { name: '내 방', exact: true }).click()
    await expect(room).toBeVisible()
  } finally {
    await studentContext.close()
  }
})
