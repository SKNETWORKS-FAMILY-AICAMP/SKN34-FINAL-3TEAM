import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #440 시작 이야기·이야기의 끝(화면 가득 재생 → 이야기, 건너뛰기, 다시 보기, 무료 일요일 다시 보기)과 장면 움직임(형식 v1) 재생.
// MSW 가상 테마(이야기 마을의 수수께끼)와 시연 미션만 쓴다(실서버·외부 호출 없음).
test.beforeEach(async ({ page }) => {
  // 한 시험에 화면 여러 개(재생 → 이야기 → 다시 보기 → 다음 화면)를 지나므로 기본 30초의 세 배
  test.slow()
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

/** 요일(월=0 … 일=6)을 정하고 가상 PIN 학생으로 들어간다. 새 브라우저 문맥이라 이야기 열람 기록이 비어 있다 */
async function student(page: Page, weekday: number) {
  await page.addInitScript(day => sessionStorage.setItem('sagomungchi:msw-weekday', String(day)), weekday)
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
}
const navigate = (page: Page, path: string) =>
  page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)
/** 목업 이야기 열람 기록(학생:주:INTRO|OUTRO) */
const storyViews = (page: Page) =>
  page.evaluate(async () => (await import('/src/mocks/fixtures/retention.ts' as string)).retentionState.storyViews as string[])
/** 목업 상태를 바꾸고 화면이 다시 받게 한다 */
async function mockTheme(page: Page, change: string, arg?: unknown) {
  await page.evaluate(async ({ change, arg }) => {
    const retention = await import('/src/mocks/fixtures/retention.ts' as string)
    const { fixtureStore, persistFixtureState } = await import('/src/mocks/fixtures/student.ts' as string)
    const { queryClient } = await import('/src/data/queryClient.ts' as string)
    const child = fixtureStore.snapshot().session.child
    if (change === 'state') {
      const { applyMockThemeState } = await import('/src/mocks/fixtures/themeState.ts' as string)
      await applyMockThemeState(child, arg, false)
    } else if (change === 'weekday') sessionStorage.setItem(retention.MOCK_WEEKDAY_KEY, String(arg))
    else if (change === 'published') {
      // 이번 주·이 학년에 관리자가 게시한 테마(그림·움직임은 arg)를 둔다
      const days = retention.themeMissions((await fixtureStore.home(child)).missions, child.grade).days
      retention.retentionState.themes = [{
        themeId: 'theme-440-fixture', grade: `G${Math.min(child.grade, 6)}`, weekStart: retention.weekStart(), title: '사라진 종소리',
        intro: '마을 종이 울리지 않아요. 무슨 일이 있었는지 하루에 하나씩 알아봐요.', status: 'PUBLISHED', updatedAt: new Date().toISOString(),
        days: days.map((d: { day: string; mission: { id: string } }) => ({ day: d.day, missionId: d.mission.id })), ...(arg as object),
      }]
    }
    retention.persistRetention()
    persistFixtureState()
    await queryClient.invalidateQueries()
  }, { change, arg })
}
/** 홈 '오늘 문제 풀기'로 시작 이야기를 연다(홈 미션 목록을 받기 전에 누르면 아무 일도 없어 다시 누름) */
async function openTodayIntro(page: Page) {
  await expect(async () => {
    if (!page.url().includes('/student/theme/intro')) await page.getByRole('button', { name: /오늘 문제 풀기/ }).click({ timeout: 3_000 })
    await expect(page).toHaveURL(/\/student\/theme\/intro/, { timeout: 3_000 })
  }).toPass({ timeout: 20_000 })
}
const noHorizontalScroll = async (page: Page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)

test('#440 시작 이야기: 그 주 처음 문제를 열면 화면 가득 재생 → 건너뛰기 → 이야기, 다시 보기, 이번 주 시작하기로 오늘 문제 안내 @responsive', async ({ page }) => {
  await student(page, 0)
  await openTodayIntro(page)
  const stage = page.getByRole('main', { name: '시작 영상' })
  await expect(stage).toBeVisible()
  // 컷 문구(captions)와 효과(effects: 별 10개, 방향 180 = 위로 떠오름)가 그림 위에
  await expect(stage.locator('.tm-caption')).toHaveText('밤마다 시계탑 종이 울렸어')
  await expect(stage.locator('.tm-fx')).toHaveCount(10)
  await noHorizontalScroll(page)
  await stage.getByRole('button', { name: '건너뛰기 →' }).click()
  const title = page.getByRole('heading', { level: 1, name: '이야기 마을의 수수께끼' })
  await expect(title).toBeFocused()
  await expect(page.locator('.tw-story-text')).toContainText('이야기 마을에서 일어난 일')
  // 이야기 화면 그림은 멈춘 그림(재생은 다시 보기로)
  await expect(page.locator('.tw-story-art .tm-player')).toHaveAttribute('data-motion', 'static')
  await expect(page.locator('.tw-story-art .tm-fx')).toHaveCount(0)
  expect((await storyViews(page)).filter(v => v.endsWith(':INTRO'))).toHaveLength(0)
  await page.getByRole('button', { name: '시작 장면 다시 보기', exact: true }).click()
  await expect(stage).toBeVisible()
  await stage.getByRole('button', { name: '건너뛰기 →' }).click()
  await page.getByRole('button', { name: '이번 주 시작하기 · 오늘 문제로 →', exact: true }).click()
  // 열람 기록(INTRO) 뒤 오늘 문제 안내로 이어감
  await expect(page.getByRole('button', { name: '미션 시작하기', exact: true })).toBeVisible()
  expect((await storyViews(page)).filter(v => v.endsWith(':INTRO'))).toHaveLength(1)
  await noHorizontalScroll(page)
})

test('#440 화면 가득 재생은 움직임·문구가 끝나면 저절로 이야기로 넘어간다', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'laptop', '움직임 길이(12초)를 기다리는 시험은 한 화면 크기에서만')
  await student(page, 0)
  await navigate(page, '/student/theme/intro')
  await expect(page.getByRole('main', { name: '시작 영상' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: '이야기 마을의 수수께끼' })).toBeVisible({ timeout: 16_000 })
})

test('#440 이야기의 끝: 정답을 맞히면 끝 장면 → 이야기와 열람 기록, 다시 보기, 무료 일요일은 되돌아보기에서 다시 보기만 @responsive', async ({ page }) => {
  await student(page, 4)
  await mockTheme(page, 'state', 'pick')
  await navigate(page, '/student/theme/pick')
  await page.getByRole('group', { name: '후보' }).getByRole('button', { name: /부엉이 선생님/ }).click()
  await page.getByRole('button', { name: '이걸로 정하기', exact: true }).click()
  await page.getByRole('button', { name: '정했어요', exact: true }).click()
  await page.getByRole('button', { name: '이야기의 끝 보기 →', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/theme\/ending/)
  const stage = page.getByRole('main', { name: '끝 영상' })
  await expect(stage).toBeVisible()
  await expect(stage.locator('.tm-caption')).toHaveText('종을 울린 건 부엉이 선생님!')
  await stage.getByRole('button', { name: '건너뛰기 →' }).click()
  await expect(page.locator('.tw-ending-title')).toBeFocused()
  await expect(page.locator('.tw-answer')).toHaveText('부엉이 선생님')
  await expect.poll(async () => (await storyViews(page)).filter(v => v.endsWith(':OUTRO')).length).toBe(1)
  await page.getByRole('button', { name: '끝 장면 다시 보기', exact: true }).click()
  await expect(stage).toBeVisible()
  await stage.getByRole('button', { name: '건너뛰기 →' }).click()
  await noHorizontalScroll(page)
  // 무료 일요일: 홈에서 새로 띄우지 않고 "이번 주 기록 보기" → 이미 본 이야기의 끝 다시 보기(기록은 늘지 않음)
  await mockTheme(page, 'weekday', 6)
  await navigate(page, '/student/home')
  await page.getByRole('button', { name: /이번 주 기록 보기/ }).click()
  await expect(page).toHaveURL(/\/student\/theme\/review/)
  await page.getByRole('button', { name: '이야기의 끝 다시 보기', exact: true }).click()
  await expect(page.getByRole('main', { name: '끝 영상' })).toBeVisible()
  await page.getByRole('button', { name: '건너뛰기 →' }).click()
  await expect(page.locator('.tw-answer')).toHaveText('부엉이 선생님')
  expect((await storyViews(page)).filter(v => v.endsWith(':OUTRO'))).toHaveLength(1)
  await noHorizontalScroll(page)
})

test('#440 움직임 줄이기면 화면 가득 재생 없이 바로 이야기(정지 그림), 문제 장면 효과도 멈춤 @responsive', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await student(page, 0)
  await openTodayIntro(page)
  await expect(page.getByRole('heading', { level: 1, name: '이야기 마을의 수수께끼' })).toBeFocused()
  await expect(page.getByRole('main', { name: '시작 영상' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '시작 장면 다시 보기', exact: true })).toHaveCount(0)
  await expect(page.locator('.tw-story-art .tm-player')).toHaveAttribute('data-motion', 'static')
  await expect(page.locator('.tm-fx')).toHaveCount(0)
  await expect(page.locator('.tm-caption')).toHaveCount(0)
  await page.getByRole('button', { name: '이번 주 시작하기 · 오늘 문제로 →', exact: true }).click()
  await page.getByRole('button', { name: '미션 시작하기', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/attempts\//)
  const scene = page.locator('.sw-side .ux-scene')
  await expect(scene.locator('img')).toBeVisible()
  await expect(scene.locator('figcaption')).toContainText('정적 장면')
  await expect(scene.locator('.tm-fx')).toHaveCount(0)
})

test('#440 문제 장면은 미션 움직임의 효과만 재생하고(카메라·살펴보기 없음) 움직임 줄이기 칸으로 멈추며 그림 크기는 그대로 @responsive', async ({ page }, testInfo) => {
  await student(page, 0)
  // 월요일 문제(시연 미션 '같은 날 심었는데')는 장면 움직임(잎 8개)과 카메라·화자·살펴보기 값을 함께 가진다
  await mockTheme(page, 'state', 'today')
  const attemptId = await page.evaluate(async () => {
    const { fixtureStore, persistFixtureState } = await import('/src/mocks/fixtures/student.ts' as string)
    const { themeMissions } = await import('/src/mocks/fixtures/retention.ts' as string)
    const child = fixtureStore.snapshot().session.child
    const days = themeMissions((await fixtureStore.home(child)).missions, child.grade).days
    const target = days.find((d: { mission: { sceneMotion?: unknown } }) => d.mission.sceneMotion)
    if (!target) throw new Error('Missing synthetic scene motion')
    const attempt = await fixtureStore.start({ ...target.mission, grade: child.grade }, child)
    persistFixtureState()
    return attempt.attemptId as string
  })
  await navigate(page, `/student/attempts/${attemptId}`)
  const scene = page.locator('.sw-side .ux-scene')
  const img = scene.locator('img')
  await expect(img).toBeVisible()
  await expect(scene.locator('.tm-fx')).toHaveCount(8)
  await expect(scene.locator('figcaption')).toContainText('움직이는 장면')
  await expect(page.locator('.tm-spot, .tm-spot-list, .tm-caption')).toHaveCount(0)
  expect(await img.evaluate(el => el.getAnimations().length), '카메라 이동 없음').toBe(0)
  // 효과 층은 그림 상자와 같은 크기
  const [imgBox, layerBox] = await Promise.all([img.boundingBox(), scene.locator('.tm-effects').boundingBox()])
  expect(Math.abs(imgBox!.width - layerBox!.width)).toBeLessThanOrEqual(4)
  expect(Math.abs(imgBox!.height - layerBox!.height)).toBeLessThanOrEqual(4)
  if (testInfo.project.name === 'laptop')
    expect(await page.locator('.st-world').evaluate(el => el.getBoundingClientRect().height)).toBeLessThanOrEqual(900)
  await scene.getByRole('checkbox', { name: '움직임 줄이기' }).check()
  await expect(scene.locator('.tm-fx')).toHaveCount(0)
  await expect(scene.locator('figcaption')).toContainText('정적 장면')
  const after = await img.boundingBox()
  expect(Math.round(after!.height)).toBe(Math.round(imgBox!.height))
  await noHorizontalScroll(page)
})

test('#440 그림 없는 수동 테마는 글만, 그림을 못 불러오면 깨진 그림 없이 글만 @responsive', async ({ page }) => {
  await student(page, 0)
  await mockTheme(page, 'published', {})
  await navigate(page, '/student/theme/intro')
  await expect(page.getByRole('heading', { level: 1, name: '사라진 종소리' })).toBeFocused()
  await expect(page.locator('.tw-story-text')).toContainText('마을 종이 울리지 않아요')
  await expect(page.locator('.tw-story-art, .tw-video-stage')).toHaveCount(0)
  await noHorizontalScroll(page)
  // 그림 주소가 깨진 테마(움직임은 계약 형식): 재생 단계도 이야기 그림도 빼고 글만
  await mockTheme(page, 'published', {
    introImageUrl: '/demo/story/missing-440.jpg',
    introMotion: { version: 1, transition: { kind: 'fade', seconds: 0.6 }, camera: { from: { x: 50, y: 50, zoom: 1 }, to: { x: 50, y: 50, zoom: 1.2 }, seconds: 10 },
      speakers: {}, effects: [], captions: [{ start: 0, end: 4, text: '종이 멈췄어요' }], spots: [] },
  })
  await navigate(page, '/student/home')
  await navigate(page, '/student/theme/intro')
  await expect(page.getByRole('heading', { level: 1, name: '사라진 종소리' })).toBeVisible()
  await expect(page.locator('.tw-story-art, .tw-video-stage')).toHaveCount(0)
  expect(await page.evaluate(() => [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.checkVisibility()).length)).toBe(0)
})

test('#441 관리자 미리보기도 같은 재생기: 계약 값(방향 숫자·전환 종류)을 재생하고, 그림을 못 불러오면 대체 칸 @responsive', async ({ page }) => {
  await page.goto('/admin/login')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  // 테마 초안 채택으로 들어온 것 같은 테마(시작 그림 주소는 깨짐, 끝 그림은 정상 + 움직임 v1)
  await page.evaluate(async () => {
    const retention = await import('/src/mocks/fixtures/retention.ts' as string)
    retention.retentionState.themes.unshift({
      themeId: 'theme-441-fixture', grade: 'G4', weekStart: '2026-11-23', title: '움직임 미리보기', intro: '시작', status: 'DRAFT',
      updatedAt: new Date().toISOString(), days: [], outro: '끝 이야기', introImageUrl: '/demo/story/missing-441.jpg', outroImageUrl: '/demo/story/outro.jpg',
      introVideoUrl: null, outroVideoUrl: null, introMotion: null,
      outroMotion: { version: 1, transition: { kind: 'zoom', seconds: 0.5 }, camera: null, speakers: {},
        effects: [{ shape: 'snow', color: '#FFFFFF', count: 6, size: 2, direction: 270, speed: 10, opacity: 0.7 }], captions: [], spots: [] },
    })
    retention.persistRetention()
  })
  await navigate(page, '/admin/themes?themeId=theme-441-fixture')
  const preview = page.getByRole('region', { name: '시작·종료 이야기 미리보기' })
  await expect(preview.getByRole('img', { name: '시작 이야기 그림을 불러오지 못했어요' })).toHaveText('그림을 불러오지 못했어요')
  await expect(preview.locator('.tm-fx')).toHaveCount(6)
  await expect(preview.locator('.tm-shot')).toHaveAttribute('data-transition', 'zoom')
  // 방향 270 = 왼쪽에서 오른쪽으로: 입자 시작 x가 그림 왼쪽 밖
  const x0 = await preview.locator('.tm-fx').first().evaluate(el => parseFloat(getComputedStyle(el).getPropertyValue('--x0')))
  expect(x0).toBeLessThan(0)
  await noHorizontalScroll(page)
})
