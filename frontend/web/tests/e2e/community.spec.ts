import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test'
// useGoogleIdentity는 React 훅이 아니라 이름만 바꿔 쓴다(oxlint rules-of-hooks)
import { newParent, useGoogleIdentity as signInWithGoogle } from './support/google.ts'
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
    const card = parentPage.getByRole('region', { name: /참여 기록/ })
    await card.getByRole('link', { name: '커뮤니티 동의하기' }).click()
    const section = parentPage.locator('#community-consent')
    // 다른 동의 목록을 불러오는 동안 "불러오고 있습니다." status가 함께 있을 수 있어 현재 상태 문구만 본다
    const state = section.getByRole('status').filter({ hasText: /^현재 / })
    await expect(state).toContainText('동의하지 않음')
    await section.getByRole('button', { name: '커뮤니티 이용에 동의' }).click()
    await expect(state).toContainText('현재 동의함')
  }
  const student = await loginStudent(browser, parentPage, nickname, `커뮤니티 ${prefix}`)
  await parentContext.close()
  return { nickname, ...student }
}

test('보호자 동의 → 친구 공개 → 같은 미션 마무리 학생이 열람·반응', async ({ browser }) => {
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
    await viewer.page.getByLabel('어떤 미션을 볼까요?').selectOption({ label: mission })
    const reactions = viewer.page.getByRole('group', { name: `${author.nickname}의 생각에 반응하기`, exact: true })
    const post = viewer.page.locator('li', { has: reactions })
    await expect(post.getByText(answer)).toBeVisible()
    const clear = reactions.getByRole('button', { name: '까닭이 잘 보여' })
    await expect(clear).toHaveAttribute('aria-pressed', 'false')
    await clear.click()
    await expect(clear).toHaveAttribute('aria-pressed', 'true')

    // 작성자의 "내가 나눈 생각"에 받은 반응 수가 보인다(FN-RET-03, 순위 없음)
    const mine = author.page.locator('section', { has: author.page.getByRole('heading', { name: '내가 나눈 생각' }) })
    await expect(async () => {
      await studentMenu(author.page, '설정')
      await studentMenu(author.page, '친구 생각')
      await expect(mine.getByText('받은 반응: 까닭이 잘 보여 1')).toBeVisible({ timeout: 3_000 })
    }).toPass({ timeout: 30_000 })
  } finally {
    for (const context of contexts) await context.close()
  }
})
