import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #648 학생 화면 시안 맞추기: 도움말·문의는 학생 틀 안, 막다른 오류 화면의 돌아가기, 뭉치 친구들, 칸 안 스크롤 없음(내 방은 PC 한 화면)
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function student(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
}
const navigate = (page: Page, path: string) =>
  page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)

test('학생 도움말·문의는 학생 틀 안 2단으로 보이고 처리 결과로 이어진다 @responsive', async ({ page }) => {
  await student(page)
  await page.locator('.st-support-menu summary').click()
  await page.getByRole('link', { name: '이용 도움말', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/help/)
  const menu = page.getByRole('navigation', { name: '학생 메뉴' })
  await expect(menu.getByRole('button', { name: '설정', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { name: '이용 도움말', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '문의·오류 신고', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '접수하기', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.getByRole('link', { name: '신고·문의 처리 결과', exact: true }).click()
  await expect(page.getByRole('heading', { name: '내 신고·문의 처리 결과' })).toBeVisible()
  await expect(menu).toBeVisible()
})

test('없는 시도로 문제 화면을 열면 홈으로 돌아가는 버튼이 있다 @responsive', async ({ page }) => {
  await student(page)
  await navigate(page, '/student/attempts/missing-648-fixture')
  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByRole('button', { name: '홈으로', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/home/)
  await expect(page.getByRole('navigation', { name: '학생 메뉴' })).toBeVisible()
})

// #648 시안 JournalDetail(사용자 의견 2026-11-16): 기록 상세는 학생 말 날짜·버전 카드·카드 안 되묻기·학생용 결과 문구, 코드·원문 시각 노출 없음
test('내 공책 기록 상세는 답 버전 카드와 학생 말로 보이고 다시 풀기로 이어진다 @responsive', async ({ page }) => {
  await student(page)
  // 기존 MSW fixture만 구성한다(합성 기록, 실서버·외부 모델 호출 없음)
  await page.evaluate(async () => {
    const { fixtureStore, persistFixtureState } = await import('/src/mocks/fixtures/student.ts' as string)
    const { demoMissions } = await import('/src/data/classroom/demoGateway.ts' as string)
    const data = fixtureStore.snapshot(), child = data.session.child
    const mission = demoMissions(child.grade)[0]
    const content = (finalAnswer: string, steps: string[]) => ({ inputType: 'SOLUTION_STEPS', text: '', finalAnswer, steps,
      essay: { claim: '', reasons: ['', ''], rebuttal: '' }, choiceIds: [], assignments: [], dictatedByGuardian: false })
    const judged = (id: string, result: string, question: string | null) => ({ status: 'DONE', nextActions: ['FINISH'],
      judgment: { judgmentId: `${id}-j`, result, trial: false, elements: [] },
      followup: question ? { followupId: `${id}-q`, type: 'LOOK_AGAIN', question, source: 'BANK' } : null })
    fixtureStore.restoreSnapshot({ ...data, attempts: [...data.attempts, {
      attemptId: 'journal-detail-648', studentId: child.id, mission, status: 'COMPLETED', finishedAt: '2026-10-24T16:00:00+09:00', helped: false,
      reflection: { difficulty: '보통', text: '곱셈으로도 셀 수 있었어요.' },
      answers: [
        { answerId: 'jd-a1', version: 1, submittedAt: '2026-10-24T15:00:00+09:00', inputType: 'SOLUTION_STEPS', text: '답: 5',
          content: content('5', ['사과를 세요', '3 + 2 = 5']), feedback: judged('jd-a1', 'RETHINK', '상자가 2개면 3을 몇 번 더해야 할까?') },
        { answerId: 'jd-a2', version: 2, submittedAt: '2026-10-24T15:05:00+09:00', inputType: 'SOLUTION_STEPS', text: '답: 6',
          content: content('6', ['3을 두 번 더해요', '3 + 3 = 6']), feedback: judged('jd-a2', 'CORRECT', null) },
      ],
    }] })
    persistFixtureState()
  })
  await navigate(page, '/student/journal')
  await page.locator('.st-journal-open', { hasText: '같은 수를 다르게 세기' }).click()
  await expect(page.getByRole('heading', { level: 1, name: '같은 수를 다르게 세기' })).toBeFocused()
  await expect(page.locator('.st-jd-tag')).toHaveText('문제 풀어 보기 · 10월 24일')
  const answers = page.getByRole('region', { name: '내 답 기록' })
  const first = answers.getByRole('article', { name: '처음 남긴 답', exact: true })
  await expect(first.getByRole('list', { name: '풀이 단계' }).getByRole('listitem')).toHaveText(['사과를 세요', '3 + 2 = 5'])
  await expect(first).toContainText('최종 답 5')
  await expect(first.locator('.st-jd-asked')).toContainText('다시 살펴보기상자가 2개면 3을 몇 번 더해야 할까?')
  await expect(answers.getByRole('article', { name: '덧붙인 답 1', exact: true }).locator('.st-jd-verdict')).toHaveText('정답을 확인했어요')
  await expect(page.getByRole('region', { name: '돌아보기와 다시 풀기' })).toContainText('이번 활동 보통이에요')
  const text = await page.locator('.st-jd-page').innerText()
  for (const code of ['DONE', 'CORRECT', 'RETHINK', 'HELD', '판정', '피드백 처리', 'T15:', '+09:00', '까닭']) expect(text, code).not.toContain(code)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.getByRole('button', { name: '다시 풀기', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/attempts\/new-/)
})

test('홈 내 포인트 카드는 뭉치 친구들로 가고, 12종 모두 만날 수 있다(곧 만나요 없음, #698) @responsive', async ({ page }) => {
  await student(page)
  await page.getByRole('button', { name: /내 포인트/ }).first().click()
  await expect(page).toHaveURL(/\/student\/friends/)
  await expect(page.getByRole('heading', { name: '뭉치 친구들', exact: true })).toBeVisible()
  const cards = page.getByRole('region', { name: '친구 목록' }).getByRole('button')
  await expect(cards).toHaveCount(12)
  await expect(cards.filter({ hasText: '곧 만나요' })).toHaveCount(0)
  await cards.filter({ hasText: '눈뭉치' }).click()
  // 새 7종도 다른 친구처럼 포인트로 만나기(잠김이면 "N 포인트로 만나기", 해금했으면 "함께 다니기")
  await expect(page.getByRole('button', { name: /포인트로 만나기$|^함께 다니기$/ })).toBeVisible()
  await expect(page.getByText('곧 만나요')).toHaveCount(0)
  await expect(cards.filter({ hasText: '솜뭉치' })).toContainText('함께 다니는 중')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

// 칸 안 스크롤 없음(사용자 의견 2026-11-16 "화면 안에 스크롤 안 해도 되게"): 내용은 다 보이고 넘치면 페이지가 내려간다.
// 내 방만 PC 한 화면 그대로(사용자 의견 2026-11-15 "스크롤을 해야 하는 게 말이 안 돼")
test('PC 1440×900에서 시안 맞춘 화면은 칸 안 스크롤이 없고, 내 방은 한 화면 안에 들어온다', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'laptop', '1440×900 기준 검사')
  await student(page)
  for (const path of ['settings', 'points', 'help', 'room', 'missions', 'journal', 'activities', 'community', 'customize?tab=furniture', 'friends', 'album']) {
    await navigate(page, `/student/${path}`)
    await expect(page.getByRole('main')).toBeVisible()
    const inner = await page.evaluate(() => [...document.querySelectorAll('.st-world *')]
      .filter(el => /(auto|scroll)/.test(getComputedStyle(el).overflowY) && el.scrollHeight > el.clientHeight + 4)
      .map(el => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`))
    expect(inner, path).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), path).toBe(false)
    if (path === 'room') expect(await page.locator('.st-world').evaluate(el => el.getBoundingClientRect().height)).toBeLessThanOrEqual(900)
  }
})

// #440 문제 푸는 화면(시안 MissionWrite·Feedback): 미션 안내와 같은 다섯 단계 칩, 메모는 답 칸을 가리지 않음, PC 한 화면·휴대전화 가로 스크롤 없음
test('#440 문제 푸는 화면은 다섯 단계 칩을 잇고 메모를 답 칸 아래에 펼친다 @responsive', async ({ page }, testInfo) => {
  await student(page)
  const attemptId = await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/student.ts'
    const { fixtureStore, persistFixtureState } = await import(path)
    const data = fixtureStore.snapshot(), child = data.session.child
    const sample = data.attempts.find((a: { mission: { inputType: string } }) => a.mission.inputType === 'NARRATIVE')
    if (!sample) throw new Error('Missing synthetic narrative mission')
    const attempt = await fixtureStore.start({ ...sample.mission, grade: child.grade }, child)
    persistFixtureState()
    return attempt.attemptId as string
  })
  await navigate(page, `/student/attempts/${attemptId}`)
  const steps = page.getByRole('list', { name: '미션 진행 단계' })
  await expect(steps.getByRole('listitem')).toHaveCount(5)
  await expect(steps.locator('[aria-current="step"]')).toHaveText('2 답변 쓰기')
  if (testInfo.project.name === 'laptop')
    expect(await page.locator('.st-world').evaluate(el => el.getBoundingClientRect().height)).toBeLessThanOrEqual(900)
  const answer = page.getByRole('textbox', { name: '내 생각과 이유', exact: true })
  await page.getByRole('button', { name: '생각 메모 · 나만 보기', exact: true }).click()
  await expect(page.getByTestId('private-memo')).toBeVisible()
  await expect(answer).toBeVisible()
  await expect(page.getByRole('button', { name: '다 썼어요', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '생각 메모 · 나만 보기', exact: true }).click()
  await answer.fill('저는 찬성해요. 그림이 있으면 이야기를 쉽게 알 수 있기 때문이에요.')
  await expect(page.locator('.ux-save-line[role=status]')).toContainText('저장했어요')
  await page.getByRole('button', { name: '다 썼어요', exact: true }).click()
  await expect(page.locator('.ux-feedback[role=status]')).not.toContainText('준비하고 있어요', { timeout: 15_000 })
  await expect(steps.locator('[aria-current="step"]')).toHaveText('3 피드백')
  // 결과 이름에 내부 말 '판정'을 쓰지 않는다(#440 26번)
  await expect(page.getByRole('region', { name: '내가 쓴 답' })).not.toContainText('판정')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

// #710 내 공책 탭: 기록 종류(context, core #700)로 "테마 문제 / 더 풀어 본 문제"를 나눈다. 미션 고르기에서 연 문제는 EXTRA로 시작한다
test('내 공책은 테마 문제와 더 풀어 본 문제 탭으로 나뉘고 화살표로 옮긴다 @responsive', async ({ page }) => {
  await student(page)
  const applied = () => page.evaluate(() => new Promise<void>(resolve =>
    addEventListener('sagomungchi:mock-theme-state-applied', () => setTimeout(resolve, 50), { once: true })))
  const done = applied()
  await page.getByRole('checkbox', { name: '프리미엄' }).setChecked(true)
  await done
  // 미션 고르기에서 문제 하나를 열어 시작(웹이 context EXTRA로 시작) → 목업에서 그 시도에 답 하나를 넣어 공책 기간 안에 둠
  await navigate(page, '/student/missions')
  await page.getByRole('button', { name: '미션 열기', exact: true }).first().click()
  await page.getByRole('button', { name: /시작하기/ }).first().click()
  await page.waitForURL('**/student/attempts/**')
  const attemptId = page.url().split('/').pop()!
  await page.evaluate(async (id) => {
    const { fixtureStore, persistFixtureState } = await import('/src/mocks/fixtures/student.ts' as string)
    const data = fixtureStore.snapshot()
    const at = data.session.period?.to ? `${data.session.period.to}T03:00:00Z` : '2026-10-24T05:00:00Z'
    fixtureStore.restoreSnapshot({ ...data, attempts: data.attempts.map((a: { attemptId: string; mission: { inputType: string } }) => a.attemptId !== id ? a : {
      ...a, status: 'COMPLETED', finishedAt: at, draft: undefined, reflection: { difficulty: '보통', text: '더 풀어 봤어요.' },
      answers: [{ answerId: 'j710', version: 1, submittedAt: at, inputType: a.mission.inputType, text: '답', content: null, feedback: null }] }) })
    persistFixtureState()
  }, attemptId)
  await navigate(page, '/student/journal')
  const tabs = page.getByRole('tablist', { name: '공책 기록 종류' })
  const theme = tabs.getByRole('tab', { name: /^테마 문제/ })
  const extra = tabs.getByRole('tab', { name: /^더 풀어 본 문제/ })
  // 처음 여는 탭은 가장 최근 기록이 든 탭(방금 마무리한 더 풀어 본 문제가 바로 보임)
  await expect(page.getByRole('tab', { selected: true })).toBeVisible()
  // 기간마다 한 번씩: 넣은 기록이 든 기간에서 더 풀어 본 문제 칸에 보인다
  const period = page.getByRole('combobox', { name: '공책 기간' })
  let found = false
  for (const value of await period.locator('option').evaluateAll((o) => o.map((x) => (x as HTMLOptionElement).value))) {
    await period.selectOption(value)
    await extra.click()
    await expect(extra).toHaveAttribute('aria-selected', 'true')
    if (await page.locator('#journal-panel .st-journal-row').count()) { found = true; break }
    await theme.click()
  }
  expect(found).toBe(true)
  await expect(extra).toContainText(/[1-9]/)
  // 테마 문제 탭으로 왼쪽 화살표(WAI-ARIA 탭)
  await extra.press('ArrowLeft')
  await expect(theme).toHaveAttribute('aria-selected', 'true')
  await expect(theme).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
