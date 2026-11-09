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
  await page.getByText('직접 새 버전 등록', { exact: true }).click()
  await expect(page.getByLabel('모델 이름')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  expect(overflow).toBe(false)
})

test('학생 생각 활동 메뉴와 섬 화면의 해 본 생각 (#240) @responsive', async ({ page }, testInfo) => {
  await studentLogin(page)
  // 최근 7일 안에 답한 합성 시도 두 건(돌아보기 있음·없음)을 MSW fixture에만 넣는다.
  await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/student.ts'
    const { fixtureStore, persistFixtureState } = await import(path)
    const data = fixtureStore.snapshot()
    const base = data.attempts.find((a: { finishedAt?: string }) => a.finishedAt)
    if (!base) throw new Error('생각 활동 화면용 완료 fixture가 없습니다.')
    const reflected = structuredClone(base), plain = structuredClone(base)
    for (const [a, id, type] of [[reflected, 'browser-activity-1', 'ANALYZE'], [plain, 'browser-activity-2', 'CREATE']] as const) {
      a.studentId = data.session.child.id; a.attemptId = id; a.mission.thinkingType = type
      a.answers[0].submittedAt = '2026-10-24T01:00:00Z'
    }
    reflected.mission.title = '합성 미션: 까닭 찾기'
    reflected.reflection = { difficulty: '보통', text: '까닭을 하나 더 찾았어요.' }
    plain.mission.title = '합성 미션: 새 방법 만들기'
    delete plain.reflection
    fixtureStore.restoreSnapshot({ ...data, attempts: [...data.attempts, reflected, plain] })
    persistFixtureState()
  })
  await page.getByRole('button', { name: '생각 활동', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/activities/)
  await expect(page.getByRole('heading', { name: '내 생각 활동', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '합성 미션: 까닭 찾기' })).toBeVisible()
  await expect(page.getByText('까닭을 하나 더 찾았어요.')).toBeVisible()
  await expect(page.getByRole('listitem').filter({ hasText: '합성 미션: 새 방법 만들기' }).getByText('아직 돌아보기를 쓰지 않았어요.')).toBeVisible()
  await expect(page.getByText(/레벨|등급|순위|점수/)).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('student-activities.png'), fullPage: true })
  // 학생 세션은 새로고침하면 PIN을 다시 받으므로 메뉴로 이동해 섬(생각 유형)을 고른다.
  await page.getByRole('button', { name: '미션 고르기', exact: true }).click()
  await page.getByRole('group', { name: '생각 유형' }).getByRole('button').nth(1).click()
  await expect(page.getByRole('heading', { name: /에서 해 본 생각$/ })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('student-island-activities.png'), fullPage: true })
})

test('학부모 분석 대화 예시 질문은 고른 질문을 현재 자녀·기간으로 보낸다 (#240)', async ({ page }, testInfo) => {
  await login(page)
  await page.goto('/parent/analysis')
  const examples = page.getByRole('group', { name: '예시 질문' })
  await expect(examples).toBeVisible()
  await expect(examples.getByRole('button')).toHaveCount(5)
  // 시연 학생은 기본 비공개(#206)라 대화 생성은 403이 될 수 있다. 여기서는 고른 질문과 범위만 확인한다.
  const scope = await page.getByText(/^선택 범위 · /).textContent()
  const create = page.waitForRequest(r => r.method() === 'POST' && new URL(r.url()).pathname === '/api/v1/conversations')
  await examples.getByRole('button', { name: '이번 주 학습 횟수는?' }).click()
  const body = (await create).postDataJSON()
  expect(scope).toContain(`${body.from} ~ ${body.to}`)
  expect(body.childId).toBeTruthy()
  await expect(page.getByRole('textbox', { name: '기록에 대한 질문' })).toHaveValue('이번 주 학습 횟수는?')
  await page.screenshot({ path: testInfo.outputPath('parent-example-questions.png'), fullPage: true })
})

test('학부모 도움말·공지·문의 접수는 core 계약 모양을 쓴다', async ({ page }) => {
  await login(page)
  await page.goto('/parent/help')
  await page.getByText('자녀와 조회 기간', { exact: true }).click()
  await expect(page.getByText('선택한 자녀와 기간의 기록만 조회합니다.', { exact: false })).toBeVisible()
  await page.goto('/parent/notices')
  await expect(page.getByText('현재 개발 시연에서는 직접 만든 예시 학생', { exact: false })).toBeVisible()
  await page.goto('/parent/support')
  await page.getByLabel('제목', { exact: true }).fill('기록 확인 문의')
  await page.getByLabel('내용', { exact: true }).fill('학습 기록은 어디서 보나요?')
  const sent = page.waitForRequest(r => r.url().endsWith('/api/v1/inquiries') && r.method() === 'POST')
  await page.getByRole('button', { name: '접수하기', exact: true }).click()
  expect((await sent).postDataJSON()).toEqual({ category: 'USAGE', title: '기록 확인 문의', body: '학습 기록은 어디서 보나요?' })
  await expect(page.getByText('기록 확인 문의', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '판정·답변 오류', exact: true }).click()
  await page.getByLabel('대상 기록 번호', { exact: true }).fill('00000000-0000-4000-8000-000000000000')
  await page.getByLabel('내용', { exact: true }).fill('판정이 이상해요')
  const report = page.waitForRequest(r => r.url().endsWith('/api/v1/error-reports') && r.method() === 'POST')
  await page.getByRole('button', { name: '접수하기', exact: true }).click()
  expect((await report).headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/)
})

test('동석 학습 뒤 보호자 비밀번호로 Google 로그인 없이 학부모 화면에 돌아온다 @responsive', async ({ page }, testInfo) => {
  await login(page)
  await page.getByRole('link', { name: '자녀 기기·PIN', exact: true }).click()
  const card = page.getByRole('region', { name: '보호자 비밀번호' })
  await expect(card.getByText('아직 없음')).toBeVisible()
  const popup = page.waitForEvent('popup')
  await card.getByRole('button', { name: '보호자 비밀번호 Google 본인 확인' }).click()
  await (await popup).close()
  await card.getByRole('button', { name: '보호자 비밀번호 완료 확인' }).click()
  await card.getByLabel('새 보호자 비밀번호', { exact: true }).fill('2580')
  await card.getByLabel('새 보호자 비밀번호 확인').fill('2580')
  await card.getByRole('button', { name: '보호자 비밀번호 정하기' }).click()
  await expect(card.getByRole('status')).toHaveText('보호자 비밀번호를 저장했습니다.')
  await expect(card.getByText('설정됨')).toBeVisible()

  await page.getByRole('button', { name: '이 자녀로 학습 시작', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/home/)
  await page.getByRole('button', { name: '학부모 로그인으로', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  const unlock = page.getByRole('form', { name: '학부모 화면으로 돌아가기' })
  await unlock.getByLabel('보호자 비밀번호').fill('1111')
  await unlock.getByRole('button', { name: '학부모 화면으로', exact: true }).click()
  await expect(unlock.getByRole('alert')).toContainText('남은 기회는 4번')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('parent-unlock.png'), fullPage: true })
  await unlock.getByLabel('보호자 비밀번호').fill('2580')
  await unlock.getByRole('button', { name: '학부모 화면으로', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await expect(page.getByLabel('자녀 선택')).toBeVisible()
})
