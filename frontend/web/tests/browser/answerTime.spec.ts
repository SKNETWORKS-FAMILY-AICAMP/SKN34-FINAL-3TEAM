import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #802 학생 답변 칸 붙여넣기·끌어다 놓기 막기(안내 문구 없음)와 생각·작성 시간 전송(P28, api-spec 3.1)
test.beforeEach(async ({ page, context }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
})

async function narrativeAttempt(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
  const attemptId = await page.evaluate(async () => {
    const { fixtureStore, persistFixtureState } = await import('/src/mocks/fixtures/student.ts' as string)
    const data = fixtureStore.snapshot(), child = data.session.child
    const sample = data.attempts.find((a: { mission: { inputType: string } }) => a.mission.inputType === 'NARRATIVE')
    const attempt = await fixtureStore.start({ ...sample.mission, grade: child.grade }, child)
    persistFixtureState()
    return attempt.attemptId as string
  })
  await page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, `/student/attempts/${attemptId}`)
  return attemptId
}
const pasteInto = async (page: Page, name: string, text: string) => {
  await page.evaluate(value => navigator.clipboard.writeText(value), text)
  await page.getByRole('textbox', { name, exact: true }).focus()
  await page.keyboard.press('ControlOrMeta+V')
}
const answerBody = (page: Page, attemptId: string) =>
  page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith(`/api/v1/attempts/${attemptId}/answers`))
    .then(r => r.postDataJSON() as Record<string, unknown>)

test('답변 칸 붙여넣기·끌어다 놓기는 막히고 메모 칸은 붙여넣기 되며, 최초·되묻기 답에 두 시간이 실린다 @responsive', async ({ page }) => {
  const attemptId = await narrativeAttempt(page)
  const answer = page.getByRole('textbox', { name: '내 생각과 이유', exact: true })
  await expect(answer).toBeVisible()
  await pasteInto(page, '내 생각과 이유', '붙여넣은 글')
  await expect(answer).toHaveValue('')
  // 끌어다 놓기도 기본 동작 취소
  expect(await answer.evaluate(el => {
    const data = new DataTransfer()
    data.setData('text/plain', '끌어 온 글')
    const event = new DragEvent('drop', { dataTransfer: data, bubbles: true, cancelable: true })
    el.dispatchEvent(event)
    return event.defaultPrevented
  })).toBe(true)
  // 안내 문구 없음(#800 결정): 답 칸 영역에 붙여넣기 안내가 생기지 않는다
  await expect(page.getByText('직접 써 볼까?')).toHaveCount(0)
  await page.getByRole('button', { name: '생각 메모 · 나만 보기', exact: true }).click()
  await page.getByTestId('private-memo').focus()
  await page.evaluate(value => navigator.clipboard.writeText(value), '메모로 붙인 글')
  await page.keyboard.press('ControlOrMeta+V')
  await expect(page.getByTestId('private-memo')).toHaveValue('메모로 붙인 글')
  await page.getByRole('button', { name: '생각 메모 · 나만 보기', exact: true }).click()
  await answer.pressSequentially('저는 찬성해요. 그림이 있으면 쉽게 알 수 있기 때문이에요.', { delay: 5 })
  await expect(page.locator('.ux-save-line[role=status]')).toContainText('저장했어요')
  const first = answerBody(page, attemptId)
  await page.getByRole('button', { name: '다 썼어요', exact: true }).click()
  const body = await first
  expect(Number.isInteger(body.thinkingSeconds)).toBe(true)
  expect(Number.isInteger(body.writingSeconds)).toBe(true)
  expect(body.thinkingSeconds as number).toBeGreaterThanOrEqual(0)
  // 되묻기 뒤 답(보완 답변)도 같은 두 칸
  await page.getByRole('button', { name: '질문에 답하기', exact: true }).click({ timeout: 15_000 })
  await pasteInto(page, '내 생각과 이유', '붙여넣은 글')
  await expect(answer).toHaveValue('')
  await answer.pressSequentially('그림을 보면 장면이 떠올라요.', { delay: 5 })
  const second = answerBody(page, attemptId)
  await page.getByRole('button', { name: '더해서 보내기', exact: true }).click()
  const followup = await second
  expect(typeof followup.followupId).toBe('string')
  expect(Number.isInteger(followup.thinkingSeconds)).toBe(true)
  expect(Number.isInteger(followup.writingSeconds)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('새로고침 뒤 이어하기·보호자 받아쓰기 제출은 두 시간을 null로 보낸다', async ({ page }) => {
  const attemptId = await narrativeAttempt(page)
  const answer = page.getByRole('textbox', { name: '내 생각과 이유', exact: true })
  await answer.fill('어제 쓰던 글이에요. 왜냐하면 그림이 좋기 때문이에요.')
  await expect(page.locator('.ux-save-line[role=status]')).toContainText('저장했어요')
  // 시연 목업은 새로고침하면 로그인이 풀리므로, 화면을 나갔다 다시 열어 같은 조건(복원된 초안이 답 칸에 있음)을 만든다
  const go = (path: string) => page.evaluate(p => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')) }, path)
  await go('/student/home')
  await waitForStudentHome(page)
  await go(`/student/attempts/${attemptId}`)
  await expect(answer).toHaveValue(/어제 쓰던 글/)
  await answer.pressSequentially(' 더 썼어요.', { delay: 5 })
  const resumed = answerBody(page, attemptId)
  await page.getByRole('button', { name: '다 썼어요', exact: true }).click()
  const body = await resumed
  expect(body.thinkingSeconds).toBeNull()
  expect(body.writingSeconds).toBeNull()
  await page.getByRole('button', { name: '질문에 답하기', exact: true }).click({ timeout: 15_000 })
  await answer.pressSequentially('보호자가 받아 적은 말이에요.', { delay: 5 })
  await page.getByRole('checkbox', { name: '보호자가 아이의 말을 그대로 적었어요.' }).check()
  const dictated = answerBody(page, attemptId)
  await page.getByRole('button', { name: '더해서 보내기', exact: true }).click()
  const guardian = await dictated
  expect(guardian.dictatedByGuardian).toBe(true)
  expect(guardian.thinkingSeconds).toBeNull()
  expect(guardian.writingSeconds).toBeNull()
})

test('저장 실패 뒤 다시 보내면 같은 멱등 키에 처음 잰 시간을 그대로 싣는다', async ({ page }) => {
  const attemptId = await narrativeAttempt(page)
  const answer = page.getByRole('textbox', { name: '내 생각과 이유', exact: true })
  await answer.pressSequentially('저는 찬성해요. 함께 보면 쉽기 때문이에요.', { delay: 5 })
  await expect(page.locator('.ux-save-line[role=status]')).toContainText('저장했어요')
  await page.getByRole('combobox', { name: '상태 시연', exact: true }).selectOption('submit-fail')
  const submit = page.getByRole('button', { name: '다 썼어요', exact: true })
  const sent: { key: string | null; body: Record<string, unknown> }[] = []
  page.on('request', r => {
    if (r.method() === 'POST' && r.url().endsWith(`/api/v1/attempts/${attemptId}/answers`))
      sent.push({ key: r.headers()['idempotency-key'] ?? null, body: r.postDataJSON() })
  })
  await submit.click()
  await expect(page.getByRole('alert')).toBeVisible()
  // 시간이 흐른 뒤 다시 보내도 작성 시간이 늘지 않아야 core 같은 요청 비교(본문 전체)를 통과한다
  await page.waitForTimeout(1_500)
  await page.getByRole('combobox', { name: '상태 시연', exact: true }).selectOption('normal')
  await submit.click()
  await expect(page.locator('.ux-feedback[role=status]')).toBeVisible()
  await expect.poll(() => sent.length).toBe(2)
  expect(sent[1].key).toBe(sent[0].key)
  expect(sent[1].body).toEqual(sent[0].body)
  expect(Number.isInteger(sent[0].body.writingSeconds)).toBe(true)
})
