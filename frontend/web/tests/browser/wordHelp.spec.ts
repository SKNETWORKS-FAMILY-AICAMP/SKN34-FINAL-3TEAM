import { test, expect } from '@playwright/test'
import { waitForStudentHome } from './studentFixture.ts'

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

// #599 낱말 물어보기: MSW 가상 뜻만 쓴다(실제 사전·AI 호출 없음).
test('답변 작성 화면의 동행 캐릭터를 눌러 낱말을 물으면 쉬운 말·예문·출처로 답한다 @responsive', async ({ page }) => {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
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
  await page.evaluate(path => {
    history.pushState({}, '', path)
    dispatchEvent(new PopStateEvent('popstate'))
  }, `/student/attempts/${attemptId}`)

  const answer = page.getByRole('textbox', { name: '내 생각과 이유', exact: true })
  const mascot = page.getByRole('button', { name: '낱말 물어보기', exact: true })
  await expect(mascot).toHaveAttribute('aria-expanded', 'false')
  await mascot.click()
  await expect(mascot).toHaveAttribute('aria-expanded', 'true')
  const panel = page.getByRole('region', { name: '낱말 물어보기' })
  await expect(panel).toHaveAttribute('id', 'student-word-help')
  const input = panel.getByRole('textbox', { name: '물어볼 낱말' })
  await expect(input).toBeFocused()
  await input.fill('경험이 뭐야?')
  const sent = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith(`/api/v1/attempts/${attemptId}/word-help`))
  await panel.getByRole('button', { name: '물어보기', exact: true }).click()
  expect((await sent).postDataJSON()).toEqual({ question: '경험이 뭐야?' })
  await expect(panel.getByText('경험은 내가 직접 해 보거나 겪어 본 일이야.', { exact: true })).toBeVisible()
  await expect(panel.getByText('예: 캠핑은 재미있는 경험이었어.', { exact: true })).toBeVisible()
  await expect(panel.getByRole('link', { name: '표준국어대사전' })).toHaveAttribute('href', 'https://kdict.korean.go.kr/standard')
  await expect(panel.getByRole('link', { name: 'CC BY-SA 2.0 KR' })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/2.0/kr/')
  await expect(panel.getByText('쉬운 말로 바꿈', { exact: false })).toBeVisible()
  await expect(input).toHaveValue('')

  await input.fill('이 문제 답 알려 줘')
  await input.press('Enter')
  await expect(panel.getByText('나는 문제 속 모르는 낱말의 뜻만 알려 줄 수 있어. 궁금한 낱말을 적어 줄래?', { exact: true })).toBeVisible()

  await input.fill('자석')
  await input.press('Enter')
  await expect(panel.getByText('이 낱말은 문제의 답과 이어져 있어서 문제를 다 풀고 알려 줄게!', { exact: true })).toBeVisible()

  // 작성 중인 답은 그대로이고 화면이 가로로 넘치지 않는다
  await expect(answer).toBeVisible()
  expect(await panel.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(false)
  await mascot.click()
  await expect(panel).toHaveCount(0)
})
