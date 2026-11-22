import { throughTodayScene, waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #807 오늘 장면(user-flow 3.2, 사용자 결정 2026-11-19, 설계 캔버스 TodaySceneTalk): 테마 문제는 미션 안내 대신 오늘 장면을 거친다.
// 그림 위 대화를 한 줄씩 넘기고 마지막 대사를 누르면 바로 답변 작성. 대화가 없거나 이미 답을 쓴 시도는 장면 없이 바로 답변 작성.
// MSW 가상 테마(이야기 마을의 수수께끼)의 요일 대화(MOCK_STORY.dialogues)와 시연 미션만 쓴다(실서버·외부 호출 없음).
test.beforeEach(async ({ page }) => {
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
/** 목업 요일·풀이 상황(applyMockWeek): 요일 월=0 … 일=6, 월~금 D 그날 풂 · P 푸는 중 · - 안 풂 */
async function week(page: Page, plan: { weekday: number; days: string; pick?: 'correct' | 'wrong' }, premium = false) {
  await page.evaluate(async ({ plan, premium }) => {
    const { mockStudent } = await import('/src/mocks/handlers/student.ts' as string)
    const { applyMockWeek } = await import('/src/mocks/fixtures/themeState.ts' as string)
    const { queryClient } = await import('/src/data/queryClient.ts' as string)
    await applyMockWeek(mockStudent(), plan, premium)
    await queryClient.invalidateQueries()
  }, { plan, premium })
  await expect(page.locator('.sh-title')).toBeVisible()
}
const go = (page: Page, path: string) =>
  page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)
const chips = (page: Page) => page.getByRole('list', { name: '이번 주 진행' })
const scene = (page: Page) => page.getByRole('main', { name: '오늘 장면' })
/** 이번 주 게시 테마를 두고 월요일 미션 사본(#882 missionSnapshots)에 움직임 값·대화를 넣는다(말꼬리·카메라 시험용) */
async function publishMonday(page: Page, motion: { speakers: Record<string, { x: number; y: number; zoom: number }>; camera: unknown }, dialogue: { speaker: string; text: string }[]) {
  await page.evaluate(async ({ motion, dialogue }) => {
    const retention = await import('/src/mocks/fixtures/retention.ts' as string)
    const { fixtureStore } = await import('/src/mocks/fixtures/student.ts' as string)
    const { queryClient } = await import('/src/data/queryClient.ts' as string)
    const child = fixtureStore.snapshot().session.child
    const days = retention.themeMissions((await fixtureStore.home(child)).missions, child.grade).days
    const snapshots = days.map(({ day, mission }: { day: string; mission: Record<string, unknown> }) => ({
      ...mission, id: 'scene807-' + day, status: undefined, attemptId: undefined,
      sceneMotion: { version: 1, transition: { kind: 'fade', seconds: 0.6 }, camera: motion.camera, speakers: motion.speakers, effects: [], captions: [], spots: [] },
    }))
    retention.retentionState.themes = [{
      themeId: 'theme-807-motion', grade: `G${Math.min(child.grade, 6)}`, weekStart: retention.weekStart(), title: '움직임 시험 테마',
      intro: '말꼬리·카메라 시험', status: 'PUBLISHED', updatedAt: new Date().toISOString(), missionSnapshots: snapshots,
      days: days.map(({ day }: { day: string }, i: number) => ({ day, missionId: snapshots[i].id, dialogue: day === 'MON' ? dialogue : null })),
    }]
    retention.persistRetention()
    await queryClient.invalidateQueries()
  }, { motion, dialogue })
  await expect(page.locator('.sh-title')).toHaveText('움직임 시험 테마')
}
const DEMO_CAMERA = { from: { x: 50, y: 50, zoom: 1 }, to: { x: 45, y: 55, zoom: 1.2 }, seconds: 12 }
/** 말꼬리 선(두 변)의 화면 영역과 끝의 기울기(SVG 단위, 0이면 곧게) */
async function tailOf(page: Page) {
  const line = scene(page).locator('.ts-tail-line')
  const box = await line.boundingBox()
  const lean = Number((await line.getAttribute('points'))?.split(' ')[1]?.split(',')[0])
  return { box: box!, lean }
}

test('홈에서 문제를 열면 오늘 장면: 대사를 한 줄씩 넘기고 마지막 대사에서 대화창 오른쪽 문제 시작하기로 답변 작성, 문제 상자에 그날 마지막 대사', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 3, days: 'DDD--' })
  await chips(page).getByRole('button', { name: '목요일 문제 풀기' }).click()
  await expect(page).toHaveURL(/\/student\/theme\/scene\/THU$/)
  // 메뉴 없음(집중), 미션 안내 없음
  await expect(page.getByRole('navigation', { name: '학생 메뉴' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '미션 시작하기' })).toHaveCount(0)
  const box = scene(page).locator('.ts-box')
  await expect(box).toHaveAttribute('data-ready', 'true')
  await expect(scene(page).locator('.ts-name')).toHaveText('뭉치')
  await expect(box).toContainText('연못가 정원도 살펴보자.')
  await expect(box).toContainText('1 / 3 · 다음 ▼')
  // 처음 푸는 문제는 대화를 다 넘기기 전에는 문제 시작하기가 없다(2026-11-22)
  const startButton = scene(page).getByRole('button', { name: /^문제 시작하기/ })
  await expect(startButton).toHaveCount(0)
  await box.click()
  await expect(scene(page).locator('.ts-name')).toHaveText('이장님')
  await expect(box).toContainText('물뿌리개 옆에 물 준 시간을 적은 표가 있어.')
  // 그림을 눌러도 다음 줄
  await scene(page).getByRole('button', { name: '다음 대사' }).click()
  await expect(box).toContainText('3 / 3')
  await expect(box).not.toContainText('다음 ▼')
  // 마지막 대사에서 대화창 오른쪽에 문제 시작하기(넓은 화면은 상자와 같은 줄 오른쪽)
  await expect(startButton).toBeVisible()
  const [boxAt, startAt] = [await box.boundingBox(), await startButton.boundingBox()]
  expect(startAt!.x).toBeGreaterThanOrEqual(boxAt!.x + boxAt!.width)
  await startButton.click()
  await expect(page).toHaveURL(/\/student\/attempts\//)
  // 답변 작성: 왼쪽 '오늘의 문제' 상자에 그날 대화 마지막 줄(뭉치가 오늘 문제로 잇는 말)
  await expect(page.locator('.sw-qtag')).toHaveText('오늘의 문제')
  await expect(page.locator('.sw-hook')).toHaveText('뭉치 · 표에 적힌 수로 같이 문제를 풀어 볼래?')
  // 장면은 주소를 바꿔치기해서 뒤로 가기는 홈으로
  await page.goBack()
  await waitForStudentHome(page)
})

test('제목 연출 중(대화 상자가 올라오기 전)에 그림을 눌러도 첫 대사를 넘기지 않는다', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 3, days: 'DDD--' })
  await go(page, '/student/theme/scene/THU')
  const box = scene(page).locator('.ts-box')
  await expect(box).toContainText('1 / 3 · 다음 ▼')
  // 준비 상태를 읽는 것과 누르기를 한 번에 한다(느린 환경에서 이미 상자가 올라왔으면 넘어가는 것이 맞아 이 확인을 건너뜀)
  const early = await page.evaluate(() => {
    const ready = document.querySelector<HTMLElement>('.ts-box')?.dataset.ready
    document.querySelector<HTMLElement>('.ts-advance')?.click()
    return ready === 'false'
  })
  test.skip(!early, '이미 대화 상자가 올라와 연출 중 누르기를 확인할 수 없음(느린 환경)')
  await expect(box).toContainText('1 / 3 · 다음 ▼')
  await expect(box).toHaveAttribute('data-ready', 'true')
  await expect(box).toContainText('1 / 3 · 다음 ▼')
})

test('말꼬리는 그 화자 위치가 있을 때만(미션 움직임 speakers), 없으면 이름표만', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: '-----' })
  // 월요일 시연 미션 움직임은 speakers에 뭉치만(x 30%)
  await go(page, '/student/theme/scene/MON')
  const box = scene(page).locator('.ts-box')
  await expect(box).toContainText('어젯밤에도 열두 시에 시계탑 종이 울렸단다.')
  await expect(scene(page).locator('.ts-name')).toHaveText('이장님')
  await expect(scene(page).locator('.ts-tail')).toHaveCount(0)
  await expect(box).toHaveAttribute('data-ready', 'true')
  await box.click()
  await box.click()
  await expect(scene(page).locator('.ts-name')).toHaveText('뭉치')
  // 말꼬리 끝은 그림 틀의 30% 자리(상자 여백과 상관없이 화면 위치로 잼)
  const frame = (await scene(page).locator('.ts-frame').boundingBox())!
  const { box: tail, lean } = await tailOf(page)
  expect(lean).toBe(0)
  expect(Math.abs(tail.x + tail.width / 2 - (frame.x + frame.width * 0.3))).toBeLessThan(3)
})

test('말꼬리 밑동은 대화 상자 안: 화자가 단추 위면 끝만 화자 쪽으로 기울고 단추와 겹치지 않음, 이름표보다 왼쪽 화자는 이름표 옆에서 왼쪽으로', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: '-----' })
  await publishMonday(page, { speakers: { 이장님: { x: 2, y: 50, zoom: 1.2 }, 뭉치: { x: 97, y: 60, zoom: 1.2 } }, camera: DEMO_CAMERA },
    [{ speaker: '이장님', text: '어젯밤에도 종이 울렸단다.' }, { speaker: '뭉치', text: '종소리 단서를 같이 따져 볼래?' }])
  await go(page, '/student/theme/scene/MON')
  const box = scene(page).locator('.ts-box')
  await expect(box).toHaveAttribute('data-ready', 'true')
  const first = await tailOf(page)
  const nameBox = (await scene(page).locator('.ts-name').boundingBox())!
  expect(first.lean).toBeLessThan(0)
  expect(first.box.x).toBeGreaterThanOrEqual(nameBox.x + nameBox.width + 10)
  await box.click()
  const start = scene(page).getByRole('button', { name: /^문제 시작하기/ })
  await expect(start).toBeVisible()
  await expect.poll(async () => (await tailOf(page)).lean).toBeGreaterThan(0)
  const last = await tailOf(page)
  const boxRect = (await box.boundingBox())!, startRect = (await start.boundingBox())!
  expect(last.box.x + last.box.width).toBeLessThanOrEqual(boxRect.x + boxRect.width - 10)
  expect(last.box.x + last.box.width).toBeLessThan(startRect.x)
})

test('처음 3초는 ai 카메라 끝 위치에서 전체 그림으로 빠지고 대사 중에는 멈춤, 카메라 값이 없으면 가운데 당기기, 움직임 줄이기면 움직이지 않음', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: '-----' })
  const art = scene(page).locator('.ts-art')
  // 시연 월요일 미션은 카메라 끝 위치 x 45·y 55·확대 1.2
  await go(page, '/student/theme/scene/MON')
  await expect(art).toBeVisible()
  await expect(art).not.toHaveClass(/ts-cam/)
  await expect.poll(() => art.evaluate((el) => el.getAnimations().map((a) => JSON.stringify((a.effect as KeyframeEffect).getKeyframes()[0].transform)).join())).toContain('scale(1.2)')
  await expect(scene(page).locator('.ts-box')).toHaveAttribute('data-ready', 'true')
  // 다 빠진 뒤에는 변환 없음(브라우저에 따라 none 또는 단위 행렬)
  await expect.poll(() => art.evaluate((el) => getComputedStyle(el).transform), { timeout: 5_000 }).toMatch(/^(none|matrix\(1, 0, 0, 1, 0, 0\))$/)

  await go(page, '/student/home')
  await publishMonday(page, { speakers: { 뭉치: { x: 30, y: 60, zoom: 1.2 } }, camera: null }, [{ speaker: '뭉치', text: '카메라 값이 없는 장면이야.' }])
  await go(page, '/student/theme/scene/MON')
  await expect(art).toHaveClass(/ts-cam/)

  await go(page, '/student/home')
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await publishMonday(page, { speakers: { 뭉치: { x: 30, y: 60, zoom: 1.2 } }, camera: DEMO_CAMERA }, [{ speaker: '뭉치', text: '움직임 줄이기 장면이야.' }])
  await go(page, '/student/theme/scene/MON')
  await expect(art).toBeVisible()
  await expect(art).not.toHaveClass(/ts-cam/)
  expect(await art.evaluate((el) => el.getAnimations().length)).toBe(0)
})

test('장면에서 홈으로 돌아가도 답을 안 쓴 시도는 이어서 풀 때 장면부터, 답을 쓰면 바로 답변 작성', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 3, days: 'DDD--' })
  await chips(page).getByRole('button', { name: '목요일 문제 풀기' }).click()
  await expect(scene(page).locator('.ts-box')).toBeVisible()
  await scene(page).getByRole('button', { name: '← 홈' }).click()
  await waitForStudentHome(page)
  // 장면에 들어오면 시도가 시작되어 '푸는 중'
  await chips(page).getByRole('button', { name: '목요일 문제 이어서 풀기' }).click()
  await throughTodayScene(page)
  await page.getByRole('textbox').first().fill('남은 무게를 구해요')
  await expect(page.getByText('저장했어요')).toBeVisible({ timeout: 10_000 })
  await go(page, '/student/home')
  await waitForStudentHome(page)
  await chips(page).getByRole('button', { name: '목요일 문제 이어서 풀기' }).click()
  await expect(page).toHaveURL(/\/student\/attempts\//)
  await expect(page.locator('.ts-box')).toHaveCount(0)
})

test('대화가 없는 날(관리자가 만든 테마 등)은 장면 없이 바로 답변 작성, 문제 상자에 대사 줄 없음', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 3, days: 'DDD--' })
  // 이번 주 게시 테마(요일 대화 없음)를 둔다
  await page.evaluate(async () => {
    const retention = await import('/src/mocks/fixtures/retention.ts' as string)
    const { fixtureStore } = await import('/src/mocks/fixtures/student.ts' as string)
    const { queryClient } = await import('/src/data/queryClient.ts' as string)
    const child = fixtureStore.snapshot().session.child
    const days = retention.themeMissions((await fixtureStore.home(child)).missions, child.grade).days
    retention.retentionState.themes = [{
      themeId: 'theme-807-fixture', grade: `G${Math.min(child.grade, 6)}`, weekStart: retention.weekStart(), title: '대화 없는 테마',
      intro: '관리자가 직접 만든 테마예요.', status: 'PUBLISHED', updatedAt: new Date().toISOString(),
      days: days.map((d: { day: string; mission: { id: string } }) => ({ day: d.day, missionId: d.mission.id })),
    }]
    retention.persistRetention()
    await queryClient.invalidateQueries()
  })
  await expect(page.locator('.sh-title')).toHaveText('대화 없는 테마')
  await chips(page).getByRole('button', { name: '목요일 문제 풀기' }).click()
  await expect(page).toHaveURL(/\/student\/attempts\//)
  await expect(page.locator('.sw-qtag')).toHaveText('오늘의 문제')
  await expect(page.locator('.sw-hook')).toHaveCount(0)
})

test('주말 되돌아보기의 다시 풀기도 오늘 장면을 거친다(마무리한 요일은 THEME_REVIEW로 시작)', async ({ page }) => {
  await student(page)
  // 정답을 틀린 토요일: 큰 단추가 주말 되돌아보기(정답을 안 골랐으면 정답 고르기)
  await week(page, { weekday: 5, days: 'DDDDD', pick: 'wrong' })
  await page.getByRole('button', { name: /주말 되돌아보기/ }).click()
  await page.getByRole('article').filter({ hasText: '금요일' }).getByRole('button', { name: '다시 풀기' }).click()
  // 목업은 THEME_REVIEW가 아니면(또는 주말이 아니면) 시작을 거부하므로 장면 대화가 나오면 종류가 맞다
  await expect(page).toHaveURL(/\/student\/theme\/scene\/FRI$/)
  await expect(scene(page).locator('.ts-box')).toContainText('종 옆 난간에서 이걸 발견했단다.')
  // 다시 풀기는 이미 본 이야기라 첫 대사부터 문제 시작하기가 보이고, 누르면 남은 대사를 건너뛴다(2026-11-22)
  await expect(scene(page).locator('.ts-box')).toHaveAttribute('data-ready', 'true')
  await expect(scene(page).locator('.ts-box')).toContainText('· 다음 ▼')
  await scene(page).getByRole('button', { name: /^문제 시작하기/ }).click()
  await expect(page).toHaveURL(/\/student\/attempts\//)
})

test('마지막 대사 상자를 눌러도 답변 작성으로 넘어간다(문제 시작하기와 같음)', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 3, days: 'DDD--' })
  await go(page, '/student/theme/scene/THU')
  await throughTodayScene(page)
  await expect(page.locator('.sw-qtag')).toHaveText('오늘의 문제')
})

test('아직 안 열린 요일 주소는 시작하지 않고 안내와 홈으로', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 1, days: 'D----' })
  await go(page, '/student/theme/scene/FRI')
  await expect(page.getByText('아직 열리지 않은 문제예요.')).toBeVisible()
  await page.getByRole('button', { name: '홈으로' }).click()
  await waitForStudentHome(page)
})

test('오늘 장면은 PC 1440×900에서 스크롤 없이 한 화면, 휴대전화는 가로 스크롤 없이 대화 상자가 그림 아래 @responsive', async ({ page }, testInfo) => {
  await student(page)
  await week(page, { weekday: 3, days: 'DDD--' })
  await go(page, '/student/theme/scene/THU')
  const box = scene(page).locator('.ts-box')
  await expect(box).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  // 홈과 같은 기준: 학생 틀이 한 화면 안(목업 띠 제외)
  if (testInfo.project.name === 'laptop')
    expect(await page.locator('.st-world').evaluate(el => el.getBoundingClientRect().height)).toBeLessThanOrEqual(900)
  const frame = await scene(page).locator('.ts-frame').boundingBox()
  const talk = await box.boundingBox()
  if (testInfo.project.name === 'compact') expect(talk!.y).toBeGreaterThanOrEqual(frame!.y + frame!.height)
  else expect(talk!.y + talk!.height).toBeLessThanOrEqual(frame!.y + frame!.height)
  // 마지막 대사의 문제 시작하기: 넓은 화면은 상자 오른쪽, 휴대전화는 상자 아래 오른쪽. 어느 쪽이든 가로 넘침 없음
  await expect(box).toHaveAttribute('data-ready', 'true')
  await box.click(); await box.click()
  const start = scene(page).getByRole('button', { name: /^문제 시작하기/ })
  await expect(start).toBeVisible()
  const [b, st] = [await box.boundingBox(), await start.boundingBox()]
  if (testInfo.project.name === 'compact') {
    expect(st!.y).toBeGreaterThanOrEqual(b!.y + b!.height)
    expect(st!.x + st!.width).toBeLessThanOrEqual(b!.x + b!.width + 1)
  } else expect(st!.x).toBeGreaterThanOrEqual(b!.x + b!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  if (testInfo.project.name === 'laptop')
    expect(await page.locator('.st-world').evaluate(el => el.getBoundingClientRect().height)).toBeLessThanOrEqual(900)
})

test('더 풀어 보기(프리미엄 추가 문제)는 그대로 미션 안내', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 3, days: 'DDD--' }, true)
  await go(page, '/student/missions')
  await page.locator('[data-open-mission]').first().click()
  await expect(page.getByRole('button', { name: '미션 시작하기' })).toBeVisible()
  await expect(page).not.toHaveURL(/\/student\/theme\/scene\//)
})

/** 문제를 마무리하고 돌아보기까지 저장한다(되묻기는 받지 않고 '이대로 돌아보기') */
async function finishAndReflect(page: Page) {
  await page.getByRole('button', { name: /^(다 썼어요|이걸로 할래요)/ }).click()
  await page.getByRole('button', { name: '이대로 돌아보기' }).click({ timeout: 20_000 })
  await page.getByRole('button', { name: '돌아보기 남기기' }).click()
  await page.getByRole('button', { name: '보통이에요' }).click()
  await page.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
}

test('문제를 마치면 미션 완료 화면: 그 요일 단서가 열렸다고 알리고 단서 모음으로 잇는다(시안 SC-02-012)', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: '-----' })
  await go(page, '/student/theme/scene/MON')
  await throughTodayScene(page)
  await page.getByRole('button', { name: /잎의 색과 크기/ }).click()
  await finishAndReflect(page)
  const done = page.getByRole('dialog', { name: '미션 완료!' })
  await expect(done).toBeVisible()
  await expect(done.getByRole('heading', { name: '미션 완료!' })).toBeFocused()
  await expect(done).toContainText('미션 학습 완료')
  await expect(done).toContainText('월요일 단서가 열렸어요!')
  await expect(done).toContainText('종 아래에 도토리 껍질이 하나도 없었어요.')
  await expect(done.getByRole('button', { name: '같은 미션 친구 생각 보기' })).toBeVisible()
  await done.getByRole('button', { name: /단서 모음 보기/ }).click()
  await expect(page).toHaveURL(/\/student\/theme\/clues$/)
})

test('금요일 문제를 마치면 마지막 단서와 정답 고르기, 금요일 친구 생각은 엔딩 전이라 없다', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: 'DDDD-' })
  await go(page, '/student/theme/scene/FRI')
  await throughTodayScene(page)
  await page.getByRole('textbox').first().fill('처음에는 어려웠지만 단서를 모으니 이유가 보였어요.')
  await expect(page.getByText('저장했어요')).toBeVisible({ timeout: 10_000 })
  await finishAndReflect(page)
  const done = page.getByRole('dialog', { name: '미션 완료!' })
  await expect(done).toContainText('마지막 단서가 열렸어요!')
  await expect(done.getByRole('button', { name: '같은 미션 친구 생각 보기' })).toHaveCount(0)
  await done.getByRole('button', { name: /정답 고르러 가기/ }).click()
  await expect(page).toHaveURL(/\/student\/theme\/pick$/)
})

test('미션 완료 화면의 같은 미션 친구 생각 보기는 그 미션을 골라 연다', async ({ page }) => {
  await student(page)
  await week(page, { weekday: 4, days: '-----' })
  await go(page, '/student/theme/scene/MON')
  await throughTodayScene(page)
  await expect(page.locator('.sw-qbox')).toBeVisible()
  const title = (await page.locator('.sw-work h1').first().textContent())?.trim() ?? ''
  await page.getByRole('button', { name: /잎의 색과 크기/ }).click()
  await finishAndReflect(page)
  await page.getByRole('dialog', { name: '미션 완료!' }).getByRole('button', { name: '같은 미션 친구 생각 보기' }).click()
  await expect(page).toHaveURL(/\/student\/community\?mission=/)
  await expect(page.getByRole('button', { name: new RegExp(title) }).first()).toHaveAttribute('aria-pressed', 'true')
})
