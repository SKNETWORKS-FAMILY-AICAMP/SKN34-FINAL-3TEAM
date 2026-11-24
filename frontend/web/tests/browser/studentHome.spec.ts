import { throughTodayScene, waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #487 학생 홈 상태별 시험(목업 "홈 상태" = 캔버스 Home 보드 8가지, user-flow 3.2·FN-RET-07·08·FN-DSH-01).
// - 공개된 문제는 지난 요일도 시작할 수 있다(카드는 가장 앞 요일, 요일 칩은 그날). 미공개 요일은 누를 수 없고, 금요일엔 다섯 개 모두
// - 무료와 프리미엄은 평일 규칙이 같다(무료는 테마 문제 주 5개, 하루 상한 없음). 일요일만 다르다: 무료는 닫힘, 프리미엄은 토요일과 같음
// - 아이 화면에는 결제 유도 문구가 없다
test.beforeEach(async ({ page }) => {
  // 문제를 여는 시험은 오늘 장면 대화 상자가 올라오기(약 3초)를 기다려 지나간다(#807). 기본 30초의 세 배
  test.slow()
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

/** 목업 위 띠의 "홈 상태"·"프리미엄"을 고르고 목업이 그 상황을 만들 때까지 기다린다. */
async function homeState(page: Page, state: string, premium = false) {
  const applied = () => page.evaluate(() => new Promise<void>(resolve =>
    addEventListener('sagomungchi:mock-theme-state-applied', () => setTimeout(resolve, 50), { once: true })))
  const box = page.getByRole('checkbox', { name: '프리미엄' })
  if ((await box.isChecked()) !== premium) {
    const done = applied()
    await box.setChecked(premium)
    await done
  }
  const done = applied()
  await page.getByRole('combobox', { name: '목업 홈 상태' }).selectOption(state)
  await done
  await expect(page.locator('.sh-title')).toBeVisible()
}

/** 홈 상태 8가지에 없는 요일·풀이 상황(목업 applyMockWeek): 요일 월=0 … 일=6, 월~금 D 그날 풂 · P 푸는 중 · - 안 풂 */
async function week(page: Page, plan: { weekday: number; days: string; pick?: 'correct' | 'wrong' }, premium = false) {
  await page.evaluate(async ({ plan, premium }) => {
    const student = '/src/mocks/handlers/student.ts', state = '/src/mocks/fixtures/themeState.ts', cache = '/src/data/queryClient.ts'
    const { mockStudent } = await import(student)
    const { applyMockWeek } = await import(state)
    const { queryClient } = await import(cache)
    await applyMockWeek(mockStudent(), plan, premium)
    await queryClient.invalidateQueries()
  }, { plan, premium })
  await expect(page.locator('.sh-title')).toBeVisible()
}

const chips = (page: Page) => page.getByRole('list', { name: '이번 주 진행' })
const chip = (page: Page, day: string) => chips(page).getByRole('listitem', { name: new RegExp(`^${day}요일 `) })
const chipButtons = (page: Page) => chips(page).getByRole('button')
const missedCard = (page: Page) => page.getByRole('button', { name: /^아직 안 푼 문제/ })
const NO_PAYMENT = /결제|구매|이용권|프리미엄/

test('#882 일반 목록에서 내려간 미션을 주간 홈·주말 다시 풀기·정답 고르기에서 게시본으로 연다', async ({ page }) => {
  await student(page)
  const ids = await page.evaluate(async () => {
    const { fixtureStore } = await import('/src/mocks/fixtures/student.ts' as string)
    const r = await import('/src/mocks/fixtures/retention.ts' as string)
    const { applyMockWeek } = await import('/src/mocks/fixtures/themeState.ts' as string)
    const { queryClient } = await import('/src/data/queryClient.ts' as string)
    const child = fixtureStore.snapshot().session.child
    const original = r.themeMissions((await fixtureStore.home(child)).missions, child.grade)
    const snapshots = original.days.map(({day,mission}:{day:string;mission:{id:string}})=>({
      ...mission, id:'pinned-'+day, title:day+' 게시본', question:day+' 게시했던 질문', status:undefined, attemptId:undefined,
    }))
    r.retentionState.themes=[{themeId:'weekly-882',grade:'G'+child.grade,weekStart:r.weekStart(),title:'게시 주간의 지도',intro:'도입',
      status:'PUBLISHED',updatedAt:new Date().toISOString(),missionSnapshots:snapshots,
      days:original.days.map(({day}:{day:string},i:number)=>({day,missionId:snapshots[i].id}))}]
    await applyMockWeek(child,{weekday:0,days:'-----'},true)
    await queryClient.invalidateQueries()
    return snapshots.map((m:{id:string})=>m.id)
  })
  await expect(page.getByRole('heading',{name:'게시 주간의 지도'})).toBeVisible()
  // 테마 문제는 오늘 장면을 거친다(#807). 게시본 요일에 대화가 없어 장면 없이 바로 답 쓰기
  await page.getByRole('button',{name:/오늘 문제 풀기/}).click()
  await page.waitForURL('**/student/attempts/**')
  await expect(page.locator('.sw-question')).toContainText('MON 게시했던 질문')
  const key = await page.evaluate(async (id:string)=>{
    const { queryClient } = await import('/src/data/queryClient.ts' as string)
    return queryClient.getQueryCache().findAll({queryKey:['mission']}).filter((q:{queryKey:unknown[]})=>q.queryKey.includes(id)).map((q:{queryKey:unknown[]})=>q.queryKey.at(-1))
  },ids[0])
  expect(key).toContain('THEME_DAY')
  const first = page.url()
  await page.goBack()
  await page.getByRole('button',{name:/이어서 풀기/}).first().click()
  await page.waitForURL('**/student/attempts/**')
  await expect(page).toHaveURL(first)
  await page.goBack()
  await week(page,{weekday:5,days:'DDDDD',pick:'wrong'},true)
  await page.getByRole('button',{name:/주말 되돌아보기/}).first().click()
  await page.locator('.tw-review-days article').last().getByRole('button',{name:'다시 풀기'}).click()
  await page.waitForURL('**/student/attempts/**')
  await expect(page.locator('.sw-question')).toContainText('FRI 게시했던 질문')
  await page.evaluate(()=>{ history.pushState({},'', '/student/theme/pick'); dispatchEvent(new PopStateEvent('popstate')) })
  await page.getByRole('button',{name:/금요일 문제 (다시|이어서) 풀기/}).click()
  await page.waitForURL('**/student/attempts/**')
  await expect(page.locator('.sw-question')).toContainText('FRI 게시했던 질문')
})

test('오늘 문제(목요일): 큰 버튼은 오늘 문제, 지난 날은 모두 풀어 카드가 없고 오늘 칩만 누를 수 있다', async ({ page }) => {
  await student(page)
  await homeState(page, 'today')
  await expect(page.getByRole('button', { name: '오늘 문제 풀기', exact: true })).toBeVisible()
  await expect(page.getByText('오늘 안에 풀면 +5 포인트')).toBeVisible()
  await expect(missedCard(page)).toHaveCount(0)
  await expect(chip(page, '수')).toHaveAccessibleName('수요일 그날 풀었어요')
  await expect(chip(page, '금')).toHaveAccessibleName('금요일 아직 안 열렸어요')
  await expect(chipButtons(page)).toHaveText(['목오늘'])
  await chips(page).getByRole('button', { name: '목요일 문제 풀기' }).click()
  await throughTodayScene(page)
})

test('안 푼 지난 문제(목요일): 화요일은 카드와 요일 칩 어느 쪽으로도 시작하고, 안 열린 금요일은 누를 수 없다', async ({ page }) => {
  await student(page)
  await homeState(page, 'behind')
  await expect(missedCard(page)).toHaveAccessibleName(/^아직 안 푼 문제 1개 · 화요일 토요일까지 풀 수 있어요/)
  await expect(chip(page, '화')).toHaveAccessibleName('화요일 아직 안 풀었어요, 토요일까지 풀 수 있어요')
  await expect(chip(page, '화').getByRole('button', { name: '화요일 문제 풀기' })).toBeVisible()
  await expect(chip(page, '금').getByRole('button')).toHaveCount(0)
  await missedCard(page).click()
  await throughTodayScene(page)
})

test('지난 요일이 여럿이면 공개된 안 푼 날마다 요일 칩으로 시작하고, 무료와 프리미엄이 같다', async ({ page }) => {
  await student(page)
  for (const premium of [false, true]) {
    // 금요일, 화·목 안 풂: 카드는 가장 앞 화요일부터, 칩은 화·목·금(오늘) 셋
    await week(page, { weekday: 4, days: 'D-D--' }, premium)
    await expect(missedCard(page)).toHaveAccessibleName(/^아직 안 푼 문제 2개 · 화·목요일 토요일까지 풀 수 있어요 · 화요일부터/)
    await expect(chipButtons(page)).toHaveCount(3)
    await expect(chips(page).getByRole('button', { name: '목요일 문제 풀기' })).toBeVisible()
    await chips(page).getByRole('button', { name: '목요일 문제 풀기' }).click()
    await throughTodayScene(page)
    // 문제 화면은 메뉴를 숨기므로 주소로 홈에 돌아간다
    await page.evaluate(() => { history.pushState({}, '', '/student/home'); dispatchEvent(new PopStateEvent('popstate')) })
    await waitForStudentHome(page)
  }
})

test('금요일에 처음 오면 다섯 문제가 모두 열려 다섯 칩 모두 누를 수 있다', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: '-----' })
  await expect(missedCard(page)).toHaveAccessibleName(/^아직 안 푼 문제 4개 · 월·화·수·목요일/)
  await expect(chipButtons(page)).toHaveCount(5)
  // 월요일(가장 앞) 문제는 그 주 처음 여는 문제가 아니어도(시작 이야기를 본 상태) 바로 오늘 장면으로 간다(#807)
  await chips(page).getByRole('button', { name: '월요일 문제 풀기' }).click()
  await throughTodayScene(page)
})

test('이어하기(목요일): 큰 버튼과 푸는 중 칩은 쓰던 문제를 바로 연다', async ({ page }) => {
  await student(page)
  await homeState(page, 'resume')
  await expect(page.getByRole('button', { name: '이어서 풀기', exact: true })).toBeVisible()
  await chips(page).getByRole('button', { name: '목요일 문제 이어서 풀기' }).click()
  await page.waitForURL('**/student/attempts/**')
})

test('정답 고르기(금요일): 단서를 다 모으면 큰 버튼이 정답 고르기이고, 맞히면 이야기의 끝으로 간다', async ({ page }) => {
  await student(page)
  // #715 4: 한 요일을 건너뛰면 4장만 모았으니 "모두"라고 하지 않는다
  await week(page, { weekday: 4, days: 'DD-DD' })
  await expect(page.getByText('단서 4장을 모았어요', { exact: true })).toBeVisible()
  await homeState(page, 'pick')
  await expect(page.getByText('단서 5장을 모두 모았어요', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /정답 고르러 가기/ }).click()
  await page.getByRole('button', { name: /부엉이 선생님/ }).first().click()
  await page.getByRole('button', { name: '이걸로 정하기' }).click()
  await page.getByRole('button', { name: '정했어요' }).click()
  await expect(page.getByText('정답이에요!')).toBeVisible()
  await page.getByRole('button', { name: /이야기의 끝 보기/ }).click()
  await page.waitForURL('**/student/theme/ending')
})

test('정답을 틀리면 평일 홈은 토요일에 다시 풀라고 하고, 토요일에는 되돌아보기에서 금요일 문제를 다시 풀 수 있다', async ({ page }) => {
  await student(page)
  await homeState(page, 'pick')
  await page.getByRole('button', { name: /정답 고르러 가기/ }).click()
  await page.getByRole('button', { name: /다람쥐 우체부/ }).first().click()
  await page.getByRole('button', { name: '이걸로 정하기' }).click()
  await page.getByRole('button', { name: '정했어요' }).click()
  await expect(page.getByText('아쉬워, 정답이 아니야')).toBeVisible()
  await page.getByRole('button', { name: '홈으로' }).click()
  await waitForStudentHome(page)
  await expect(page.getByText('토요일에 금요일 문제를 다시 풀면 이야기의 끝을 볼 수 있어요.')).toBeVisible()
  // 금요일 뒤에는 새 문제가 없다("다음 요일에 새 문제가 열려요"라고 하지 않음)
  await expect(page.getByText('이번 주 문제를 모두 풀었어요.')).toBeVisible()

  await week(page, { weekday: 5, days: 'DDDDD', pick: 'wrong' })
  await expect(page.getByText('토요일에 금요일 문제를 다시 풀면')).toHaveCount(0)
  await page.getByRole('button', { name: /주말 되돌아보기/ }).click()
  await expect(page.getByRole('article').filter({ hasText: '금요일' }).getByRole('button', { name: '다시 풀기' })).toBeVisible()
  await expect(page.getByText(/금요일 정답 고르기를 틀렸다면/)).toBeVisible()
})

test('엔딩 뒤(금요일): 큰 버튼은 이야기의 끝 다시 보기, 정답을 알려 준다', async ({ page }) => {
  await student(page)
  await homeState(page, 'ended')
  await expect(page.getByRole('button', { name: /이야기의 끝 다시 보기/ })).toBeVisible()
  await expect(page.getByText('정답은 부엉이 선생님이었어요!')).toBeVisible()
})

test('토요일: 큰 버튼은 주말 되돌아보기, 안 푼 금요일은 오늘까지 풀 수 있고 마무리한 날 칩은 누르지 않는다', async ({ page }) => {
  await student(page)
  await homeState(page, 'sat')
  await expect(page.getByRole('button', { name: /주말 되돌아보기/ })).toBeVisible()
  await expect(missedCard(page)).toHaveAccessibleName(/^아직 안 푼 문제 1개 · 금요일 오늘까지 풀 수 있어요/)
  await expect(chip(page, '금')).toHaveAccessibleName('금요일 아직 안 풀었어요, 오늘까지 풀 수 있어요')
  // 다시 풀기는 주말 되돌아보기에서(칩은 지금 새로 시작·이어서 할 수 있는 날만)
  await expect(chipButtons(page)).toHaveCount(1)
  await chips(page).getByRole('button', { name: '금요일 문제 풀기' }).click()
  await throughTodayScene(page)
})

test('일요일(무료): 이번 주 테마가 끝났어요, 풀기·정답 고르기 없이 기록과 본 엔딩 다시 보기만, 결제 문구 없음', async ({ page }) => {
  await student(page)
  await homeState(page, 'sun')
  await expect(page.getByRole('button', { name: /이번 주 기록 보기/ })).toBeVisible()
  await expect(page.getByText('이번 주 테마가 끝났어요.')).toBeVisible()
  await expect(page.getByRole('button', { name: /모은 단서/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /정답 고르러 가기/ })).toHaveCount(0)
  await expect(chipButtons(page)).toHaveCount(0)
  await expect(page.getByRole('main')).not.toContainText(NO_PAYMENT)

  // 안 푼 날이 있어도 닫힘(카드·칩 버튼 없음), 틀린 학생에게 "토요일에 다시 풀면"을 말하지 않음
  await week(page, { weekday: 6, days: 'DDDD-', pick: 'wrong' })
  await expect(chip(page, '금')).toHaveAccessibleName('금요일 풀지 못했어요')
  await expect(missedCard(page)).toHaveCount(0)
  await expect(chipButtons(page)).toHaveCount(0)
  await expect(page.getByText('토요일에 금요일 문제를 다시 풀면')).toHaveCount(0)
  // 시작 이야기 다시 보기는 되지만 "이번 주 시작하기"(열람 기록)는 없다
  await page.getByRole('button', { name: '시작 이야기 다시 보기' }).click()
  await page.getByRole('button', { name: '건너뛰기 →' }).click()
  await expect(page.getByRole('button', { name: /이번 주 시작하기/ })).toHaveCount(0)
  await page.getByRole('button', { name: '홈으로', exact: true }).click()
  await waitForStudentHome(page)

  // 엔딩을 본 주: 되돌아보기 닫힘 화면에서 이야기의 끝 다시 보기
  await week(page, { weekday: 6, days: 'DDDDD', pick: 'correct' })
  await page.getByRole('button', { name: /이번 주 기록 보기/ }).click()
  await expect(page.getByRole('heading', { name: '이번 주 테마는 끝났어요' })).toBeVisible()
  await expect(page.getByRole('button', { name: '이야기의 끝 다시 보기' })).toBeVisible()
  await expect(page.getByRole('main')).not.toContainText(NO_PAYMENT)
})

test('일요일(프리미엄): 토요일과 같이 안 푼 문제 풀기·되돌아보기·정답 고르기, 결제 문구 없음', async ({ page }) => {
  await student(page)
  await homeState(page, 'sun', true)
  await expect(page.getByRole('button', { name: /정답 고르러 가기/ })).toBeVisible()
  await expect(page.getByText('이번 주 테마가 끝났어요.')).toHaveCount(0)

  await week(page, { weekday: 6, days: 'DDDD-' }, true)
  await expect(page.getByRole('button', { name: /주말 되돌아보기/ })).toBeVisible()
  await expect(missedCard(page)).toHaveAccessibleName(/오늘까지 풀 수 있어요/)
  await expect(page.getByRole('main')).not.toContainText(NO_PAYMENT)
  await chips(page).getByRole('button', { name: '금요일 문제 풀기' }).click()
  await throughTodayScene(page)
})

test('테마 없음: 준비 중 안내와 내 공책·더 풀어 보기', async ({ page }) => {
  await student(page)
  await homeState(page, 'none')
  await expect(page.getByRole('heading', { name: '이번 주 테마를 준비하고 있어요' })).toBeVisible()
  await expect(page.getByRole('button', { name: '내 공책 보기' })).toBeVisible()
  await expect(page.getByRole('button', { name: /더 풀어 보기/ })).toBeVisible()
})

test('홈 상태마다 PC 1440×900은 학생 틀이 한 화면 안, 휴대전화는 가로 스크롤 없음 @responsive', async ({ page }, testInfo) => {
  await student(page)
  for (const state of ['today', 'behind', 'resume', 'pick', 'ended', 'sat', 'sun', 'none']) {
    await homeState(page, state)
    if (testInfo.project.name === 'laptop')
      expect(await page.locator('.st-world').evaluate(el => el.getBoundingClientRect().height), state).toBeLessThanOrEqual(900)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), state).toBe(false)
  }
  // 안 푼 날이 가장 많은 금요일 첫 방문(카드 글이 가장 김)
  await week(page, { weekday: 4, days: '-----' })
  if (testInfo.project.name === 'laptop')
    expect(await page.locator('.st-world').evaluate(el => el.getBoundingClientRect().height)).toBeLessThanOrEqual(900)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

// #715 1번: 엔딩 뒤에는 특징 표 전체로 후보 카드를 채운다. 건너뛴 요일 특징은 "엔딩 뒤 공개", 엔딩 전에는 단서만
const go = (page: Page, path: string) =>
  page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)
test('단서 모음 후보 카드: 엔딩 전에는 푼 요일 단서만, 엔딩 뒤에는 건너뛴 요일 특징도 엔딩 뒤 공개로', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: 'DD-DD' })
  await go(page, '/student/theme/clues')
  const owl = page.getByRole('list', { name: '부엉이 선생님에 대해 알아낸 것' })
  await expect(owl.getByRole('listitem')).toHaveCount(4)
  await expect(owl).not.toContainText('엔딩 뒤 공개')
  await go(page, '/student/home')
  await week(page, { weekday: 5, days: 'DD-DD', pick: 'correct' })
  await go(page, '/student/theme/clues')
  await expect(owl.getByRole('listitem')).toHaveCount(5)
  await expect(owl.getByRole('listitem').filter({ hasText: '엔딩 뒤 공개' })).toHaveCount(1)
  // 요일별 단서의 건너뛴 수요일 칸도 엔딩 뒤에는 "마치면 열려요" 대신 후보 카드를 가리킴
  await expect(page.getByText('수요일 문제를 마치면 열려요.')).toHaveCount(0)
  await expect(page.locator('.tw-clue-top').filter({ hasText: '못 얻은 단서' })).toHaveCount(1)
})
