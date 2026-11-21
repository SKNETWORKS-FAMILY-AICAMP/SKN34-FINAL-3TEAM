import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test'
// useGoogleIdentity는 React 훅이 아니라 이름만 바꿔 쓴다(oxlint rules-of-hooks)
import { admin, newParent, useGoogleIdentity as signInWithGoogle } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, solveNarrative, startExtraMission, studentMenu } from './support/student.ts'

// 추가 문제(EXTRA)라 요일과 무관하다. 공유물은 돌아보기 저장 때 작성자가 공개 상태일 때만 생긴다(FN-RET-01·02)
const mission = '쉬는 시간을 늘린다면?' // demo_missions.sql 2번 (초3·NARRATIVE)

async function newStudent(browser: Browser, prefix: string, consent: boolean) {
  const nickname = `${prefix}${Date.now().toString(36)}`
  const parentContext = await browser.newContext()
  await signInWithGoogle(parentContext, newParent('community'))
  const parentPage = await parentContext.newPage()
  await onboardParent(parentPage, nickname)
  if (consent) {
    // 계정·자녀 설정 › 공개·동의 › 풀이 공유 커뮤니티(선택 동의 COMMUNITY)
    await parentPage.getByRole('button', { name: '참여 기록', exact: true }).click()
    const card = parentPage.getByRole('dialog').getByRole('region', { name: /참여 기록/ })
    await card.getByRole('link', { name: '커뮤니티 동의하기' }).click()
    const section = parentPage.locator('#community-consent')
    // 다른 동의 목록을 불러오는 동안 "불러오고 있습니다." status가 함께 있을 수 있어 현재 상태 문구만 본다
    const state = section.getByRole('status').filter({ hasText: /^현재 / })
    await expect(state.getByText('동의하지 않음', { exact: true })).toBeVisible()
    await section.getByRole('button', { name: '커뮤니티 이용에 동의' }).click()
    await expect(state.getByText('동의함', { exact: true })).toBeVisible()
  }
  const student = await loginStudent(browser, parentPage, nickname, `커뮤니티 ${prefix}`)
  await parentContext.close()
  return { nickname, ...student }
}

test('친구 공개·열람 → 신고로 숨김 → 관리자 재공개 → 학생 열람·반응', async ({ browser }) => {
  const contexts: BrowserContext[] = []
  try {
    const author = await newStudent(browser, '작성', true)
    contexts.push(author.context)
    const sharing = (page: Page) => page.getByRole('region', { name: '친구들에게 내 답 보여 주기' })
    const friends = (page: Page) => sharing(page).getByRole('radio', { name: /친구들에게 보여 줄게요/ })
    await studentMenu(author.page, '설정')
    await expect(friends(author.page)).toBeEnabled()
    await expect(sharing(author.page).getByText('보호자 동의가 필요해요')).toHaveCount(0)
    await friends(author.page).click()
    await expect(friends(author.page)).toBeChecked()
    await expect(sharing(author.page).getByText('친구 공개 켜짐')).toBeVisible()
    const answer = '저는 찬성이에요. 쉬는 시간에 몸을 움직이면 다음 시간에 더 집중할 수 있기 때문이에요.'
    await startExtraMission(author.page, mission)
    await solveNarrative(author.page, answer)

    // 열람자는 공개 설정·동의 없이도 같은 미션을 마무리했으면 볼 수 있다
    const viewer = await newStudent(browser, '열람', false)
    contexts.push(viewer.context)
    await studentMenu(viewer.page, '친구 생각')
    await expect(viewer.page.getByText('아직 마무리한 미션이 없어요', { exact: false })).toBeVisible()
    await startExtraMission(viewer.page, mission)
    await solveNarrative(viewer.page, '저는 반대예요. 쉬는 시간이 길면 하교 시간이 늦어지기 때문이에요.')
    await studentMenu(viewer.page, '친구 생각')
    await expect(viewer.page.getByRole('heading', { name: '친구 생각' })).toBeVisible()
    // #648 친구 생각은 미션 고르기 select 대신 왼쪽 "어떤 미션을 볼까요?" 버튼 목록
    await viewer.page.getByRole('group', { name: '어떤 미션을 볼까요?' }).getByRole('button', { name: mission }).click()
    const reactions = viewer.page.getByRole('group', { name: `${author.nickname}의 생각에 반응하기`, exact: true })
    const post = viewer.page.locator('li', { has: reactions })
    await expect(post.getByText(answer)).toBeVisible()
    const comment = `공유물 신고 시연 ${viewer.nickname}`
    await post.getByRole('button', { name: '이상한 글 신고' }).click()
    await post.getByRole('textbox').fill(comment)
    const submitted = viewer.page.waitForResponse((response) =>
      new URL(response.url()).pathname === '/api/v1/error-reports' && response.request().method() === 'POST')
    await post.getByRole('button', { name: '신고하기', exact: true }).click()
    const submission = await submitted
    expect(submission.status()).toBe(201)
    const { reportId } = await submission.json() as { reportId: string }
    await expect(post).toHaveCount(0)

    const adminContext = await browser.newContext()
    contexts.push(adminContext)
    await signInWithGoogle(adminContext, admin)
    const adminPage = await adminContext.newPage()
    await adminPage.goto('/admin/login')
    await adminPage.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
    await adminPage.waitForURL('**/admin/home**')
    await adminPage.getByRole('link', { name: '오류 신고', exact: true }).click()
    const waitForOriginal = () => adminPage.waitForResponse((response) =>
      new URL(response.url()).pathname === `/api/v1/admin/error-reports/${reportId}` && response.request().method() === 'GET')
    const hidden = waitForOriginal()
    await adminPage.locator('article', { hasText: comment }).getByRole('button', { name: '신고 상세·연결 기록 열람' }).click()
    expect((await (await hidden).json()).linkedPost.status).toBe('HIDDEN_REPORT')
    const report = adminPage.getByRole('dialog', { name: '신고 연결 기록 검토' })
    await expect(report.getByText(answer, { exact: true })).toBeVisible()
    await report.getByRole('textbox', { name: '검토 사유' }).fill('공유물 원문 확인')
    await report.getByRole('button', { name: '검토 시작' }).click()
    const decision = report.getByLabel('공유물 처리 결과')
    await expect(decision).toHaveValue('REMOVED')
    await decision.selectOption('VISIBLE')
    await report.getByRole('textbox', { name: '검토 사유' }).fill('다시 공개할 수 있는 답변입니다.')
    const save = report.getByRole('button', { name: '검토 결과 저장' })
    await expect(save).toBeEnabled()
    const restored = waitForOriginal()
    await save.click()
    expect((await (await restored).json()).linkedPost.status).toBe('VISIBLE')
    await expect(report.getByRole('heading', { name: '검토 완료 · 다시 공개' })).toBeVisible()
    await expect(decision).toHaveCount(0)

    // 학습 서비스까지 반영된 공유물을 새로 조회한다.
    await studentMenu(viewer.page, '홈')
    await studentMenu(viewer.page, '친구 생각')
    await viewer.page.getByRole('group', { name: '어떤 미션을 볼까요?' }).getByRole('button', { name: mission }).click()
    await expect(post.getByText(answer)).toBeVisible()

    // 학생 화면 "까닭" → "이유"(사용자 결정 2026-11-15, REACTION_LABELS.CLEAR_REASON)
    const clear = reactions.getByRole('button', { name: '이유가 잘 보여' })
    await expect(clear).toHaveAttribute('aria-pressed', 'false')
    await clear.click()
    await expect(clear).toHaveAttribute('aria-pressed', 'true')

    // 작성자의 "내가 나눈 생각"에 받은 반응 수가 보인다(FN-RET-03, 순위 없음)
    // #648: "내가 나눈 생각"은 친구 생각 화면의 "내가 나눈 생각 보기" 버튼으로 오른쪽 칸을 바꿔 보여 준다
    const mine = author.page.getByRole('region', { name: '내가 나눈 생각' })
    await expect(async () => {
      await studentMenu(author.page, '설정')
      await studentMenu(author.page, '친구 생각')
      await author.page.getByRole('button', { name: '내가 나눈 생각 보기' }).click()
      await expect(mine.getByText('받은 반응: 이유가 잘 보여 1')).toBeVisible({ timeout: 3_000 })
    }).toPass({ timeout: 30_000 })

    // #709 친구 방 놀러 가기(실서버 core #708·learning #707): 열람자가 작성자 글에서 그 방에 놀러 간다
    const visit = post.getByRole('button', { name: `${author.nickname}의 방에 놀러 가기` })
    const backToPosts = viewer.page.getByRole('button', { name: /친구 생각으로 돌아가기/ })
    await visit.click()
    await expect(viewer.page.getByRole('heading', { name: `${author.nickname}의 방에 놀러 왔어요` })).toBeVisible()
    const room = viewer.page.getByRole('region', { name: `${author.nickname}의 방` })
    await expect(room.locator('.st-friend-name')).toHaveText(author.nickname)
    await expect(viewer.page.getByRole('button', { name: '방 꾸미기' })).toHaveCount(0)
    await expect(room.getByRole('button', { name: /^액자 크게 보기: / })).toHaveCount(0) // 새 학생이라 걸린 액자 없음

    // 작성자가 친구 공개를 끄면 같은 글에서 다시 놀러 갈 수 없고, 이유는 말하지 않는다(404 COMMUNITY_POST_NOT_FOUND)
    await studentMenu(author.page, '설정')
    await sharing(author.page).getByRole('radio', { name: '나만 볼게요' }).click()
    await expect(sharing(author.page).getByText('친구 공개 꺼짐')).toBeVisible()
    await backToPosts.click()
    await expect(post.getByText(answer)).toBeVisible() // 목록은 아직 예전 것(친구 생각 화면을 숨겨 두었을 뿐)
    await visit.click()
    await expect(viewer.page.getByRole('alert')).toContainText('지금은 이 친구 방에 놀러 갈 수 없어요.')
    await backToPosts.click()
    await expect(viewer.page.getByText(answer)).toHaveCount(0) // 404 뒤 목록을 다시 받아 그 글이 빠짐
  } finally {
    for (const context of contexts) await context.close()
  }
})
