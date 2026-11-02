import { writeFile } from 'node:fs/promises'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  // 외부 글꼴이나 외부 API의 성공에 의존하지 않는 기존 MSW 앱 화면 테스트.
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function login(page: Page, role: 'parent' | 'admin' = 'parent', email?: string) {
  await page.goto(role === 'admin' ? '/admin/login' : '/login')
  if (email) await page.getByRole('textbox', { name: '이메일', exact: true }).fill(email)
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(role === 'admin' ? /\/admin\/home/ : /\/parent\/journal/)
}

async function studentLogin(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await expect(page).toHaveURL(/\/student\/home/)
}

test('학생 공개 설정 @responsive', async ({ page }, testInfo) => {
  await studentLogin(page)
  await page.getByRole('button', { name: '공개 설정', exact: true }).click()
  await expect(page.getByRole('heading', { name: '내 답 공개 설정', exact: true })).toBeVisible()
  await expect(page.getByRole('radio', { name: '비공개로 둘게요' })).toBeChecked()
  await page.getByRole('radio', { name: '학부모님께 공개할게요' }).click()
  await expect(page.getByRole('status').filter({ hasText: '현재 공개 상태입니다.' })).toBeVisible()
  await page.getByRole('radio', { name: '비공개로 둘게요' }).click()
  await expect(page.getByRole('status').filter({ hasText: '현재 비공개 상태입니다.' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('student-sharing.png'), fullPage: true })
  await writeFile(testInfo.outputPath('sharing-rendered.html'), (await page.content()).replace(/<script\b[\s\S]*?<\/script>/gi, ''))
})

test('학생 결과의 이전·현재 공책 비교 @responsive', async ({ page }, testInfo) => {
  await studentLogin(page)
  // 기존 MSW fixture만 구성한다. 실서버·학생 원문·외부 모델 호출은 사용하지 않는다.
  await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/student.ts'
    const { fixtureStore, persistFixtureState } = await import(path)
    const data = fixtureStore.snapshot()
    const childId = data.session.child.id
    const base = data.attempts.find((a: { studentId: string; finishedAt?: string }) => a.finishedAt)
    if (!base) throw new Error('비교 화면용 완료 fixture가 없습니다.')
    const previous = structuredClone(base), current = structuredClone(base)
    previous.studentId = childId
    current.studentId = childId
    previous.attemptId = 'browser-previous'
    previous.finishedAt = '2026-10-31T01:00:00Z'
    previous.answers[0].text = '이전에 쓴 합성 답입니다.'
    current.attemptId = 'browser-current'
    current.finishedAt = '2026-11-01T01:00:00Z'
    current.answers[0].text = '이번에는 까닭을 보탠 합성 답입니다.'
    fixtureStore.restoreSnapshot({ ...data, attempts: [...data.attempts, previous, current] })
    persistFixtureState()
    history.pushState({}, '', '/student/attempts/browser-current')
    dispatchEvent(new PopStateEvent('popstate'))
  })
  const panel = page.getByRole('region', { name: '이전 답과 이번 답 비교' })
  await expect(panel).toBeVisible()
  await expect(panel.getByRole('heading', { name: '이전 답', exact: true })).toBeVisible()
  await expect(panel.getByRole('heading', { name: '이번 답', exact: true })).toBeVisible()
  await expect(panel.getByText('이전에 쓴 합성 답입니다.', { exact: true })).toBeVisible()
  await expect(panel.getByText('이번에는 까닭을 보탠 합성 답입니다.', { exact: true })).toBeVisible()
  expect(await panel.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(false)
  await panel.screenshot({ path: testInfo.outputPath('attempt-comparison.png') })
  await writeFile(testInfo.outputPath('comparison-rendered.html'), (await page.content()).replace(/<script\b[\s\S]*?<\/script>/gi, ''))
  await page.getByRole('button', { name: '이 미션 다시 풀기', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/attempts\/new-/)
  await expect(page.getByRole('region', { name: '이전 답과 이번 답 비교' })).toHaveCount(0)
  const originals = await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/student.ts'
    const { fixtureStore } = await import(path)
    return fixtureStore.snapshot().attempts.filter((a: { attemptId: string }) => ['browser-previous', 'browser-current'].includes(a.attemptId))
      .map((a: { answers: { text: string }[] }) => a.answers[0].text)
  })
  expect(originals).toEqual(['이전에 쓴 합성 답입니다.', '이번에는 까닭을 보탠 합성 답입니다.'])

})

test('학부모 로그인 → 자녀별 기록 → 이용권·결제 화면', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await login(page)
  await expect(page.getByLabel('자녀 선택')).toBeVisible()
  await page.getByRole('link', { name: '이용권·결제', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/billing/)
  await expect(page.getByRole('heading', { name: '이용권·결제', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '이용권 선택', exact: true })).toBeVisible()
  await expect(page.getByRole('radio').first()).toBeVisible()
  expect(errors).toEqual([])
})

test('학생 시연 기기 준비 → PIN 인증 → 학생 홈', async ({ page }) => {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await expect(page).toHaveURL(/\/student\/home/)
  await expect(page.getByRole('heading', { name: /학습 홈/ })).toBeAttached()
})

test('관리자 큐·DLQ와 작업 재처리의 선택 상태를 분리한다', async ({ page }) => {
  await login(page, 'admin')
  await page.getByRole('link', { name: '큐·DLQ', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/queues/)
  await expect(page.getByRole('link', { name: '큐·DLQ', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('link', { name: '작업 재처리', exact: true })).not.toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { name: /큐.*DLQ/ }).first()).toBeVisible()
})

test('운영 전용 관리자는 결제 메뉴가 없고 모델 운영 화면을 사용할 수 있다', async ({ page }) => {
  await login(page, 'admin', 'ops@example.test')
  await expect(page.getByRole('link', { name: '결제·환불', exact: true })).toHaveCount(0)
  // SPA 내에서 권한 없는 경로로 이동해 동일 세션의 접근 제어를 검증한다.
  await page.getByRole('link', { name: '모델·프롬프트', exact: true }).click()
  await expect(page.getByRole('heading', { name: '모델·프롬프트 버전', exact: true })).toBeVisible()
  await expect(page.getByLabel('모델 이름')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  expect(overflow).toBe(false)
})
