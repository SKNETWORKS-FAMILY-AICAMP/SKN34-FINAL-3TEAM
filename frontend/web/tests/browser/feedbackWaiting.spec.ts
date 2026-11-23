import path from 'node:path'
import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #847 피드백 대기 표시: 단계 문구·움직임, 결과 즉시 표시, 실패 버튼, 새로고침 이어받기, 겹침, 움직임 줄이기
const shots = path.resolve(process.cwd(), '../../output')
const shot = (page: Page, name: string) => page.screenshot({ path: path.join(shots, `847-${name}.png`) })

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

/** 시연 학생 로그인. accessory면 로그인 전에 그 소품(ACC_LIGHT 손전등·ACC_LENS 돋보기)을 입혀 둔다(새로고침하면 학생 세션이 풀려서) */
async function login(page: Page, accessory?: 'ACC_LIGHT' | 'ACC_LENS') {
  await page.goto('/student/login')
  if (accessory)
    await page.evaluate(async (code) => {
      const { mockLooks, persistLooks } = await import('/src/mocks/fixtures/studentLook.ts' as string)
      const { pinDemoChild } = await import('/src/mocks/fixtures/studentPinDemo.ts' as string)
      const look = mockLooks.get(pinDemoChild.id) ?? { theme: 'lake', companion: 'mungchi' }
      mockLooks.set(pinDemoChild.id, { ...look, equipped: { HAT: 'HAT_ACORN', OUTFIT: null, ACCESSORY: code, BACKGROUND: null } })
      persistLooks()
    }, accessory)
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
}
/** 글쓰기 미션 시도를 새로 열어 둔다. running이면 답을 하나 보내 둔 채 RUNNING(보낸 지 runningFor초)으로 만들어 둔다 */
async function openAttempt(page: Page, running?: { seconds: number }) {
  const attemptId = await page.evaluate(async (running) => {
    const { fixtureStore, persistFixtureState } = await import('/src/mocks/fixtures/student.ts' as string)
    const { blankAnswer } = await import('/src/domain/classroom.ts' as string)
    const data = fixtureStore.snapshot(), child = data.session.child
    const sample = data.attempts.find((a: { mission: { inputType: string } }) => a.mission.inputType === 'NARRATIVE')
    const attempt = await fixtureStore.start({ ...sample.mission, grade: child.grade }, child)
    if (running) {
      await fixtureStore.submit(attempt.attemptId, { ...blankAnswer('NARRATIVE'), text: '나는 찬성해요. 그림이 있으면 쉽기 때문이에요.' }, crypto.randomUUID())
      const snap = fixtureStore.snapshot()
      const a = snap.attempts.find((x: { attemptId: string }) => x.attemptId === attempt.attemptId)
      const last = a.answers.at(-1)
      last.feedback = { status: 'RUNNING', nextActions: [] }
      last.submittedAt = new Date(Date.now() - running.seconds * 1000).toISOString()
      fixtureStore.restoreSnapshot(snap)
    }
    persistFixtureState()
    return attempt.attemptId as string
  }, running)
  return attemptId
}
const go = (page: Page, attemptId: string) =>
  page.evaluate(p => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')) }, `/student/attempts/${attemptId}`)
const scenario = (page: Page, value: string) => page.getByRole('combobox', { name: '상태 시연', exact: true }).selectOption(value)
async function writeAndSend(page: Page) {
  const answer = page.getByRole('textbox', { name: '내 생각과 이유', exact: true })
  await answer.fill('저는 찬성해요. 그림이 있으면 쉽게 알 수 있기 때문이에요.')
  await expect(page.locator('.ux-save-line[role=status]')).toContainText('저장했어요')
  await page.getByRole('button', { name: '다 썼어요', exact: true }).click()
}
const box = (page: Page) => page.locator('.ux-feedback[role=status]')
const anim = (page: Page, sel: string) => page.locator(sel).first().evaluate(e => getComputedStyle(e).animationName)
const bubble = (page: Page) => page.locator('.sw-wait-bubble')

test('40초 늦는 피드백: 문구가 차례로 바뀌고 결과가 오면 바로 피드백 상자, "찾았다!"는 잠깐만', async ({ page }) => {
  await page.clock.install()
  await login(page)
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  const wait = page.locator('.sw-wait')
  await expect(wait).toBeVisible()
  // 피드백 상자 하나만 화면 읽기 영역이고 그림·말풍선은 숨김, 단계 문구는 숨김 글자로 한 번
  await expect(box(page)).toHaveCount(1)
  await expect(page.locator('.sw-wait [role=status]')).toHaveCount(0)
  await expect(bubble(page)).toHaveAttribute('aria-hidden', 'true')
  await expect(page.locator('.sw-wait-poke')).toHaveAttribute('aria-hidden', 'true')
  await expect(page.locator('.sw-wait-ground')).toHaveAttribute('aria-hidden', 'true')
  await expect(box(page)).toContainText('답을 꼼꼼히 읽고 있어')
  // 대기 중 제목은 대기 화면 전용 문장(공책 기록 상세의 처리 중 문장과 따로)
  await expect(box(page).locator('h2')).toHaveText('피드백을 만드는 중이에요')
  await expect(page.getByRole('progressbar')).toHaveCount(0)
  await expect(wait).toHaveAttribute('data-motion', 'look')
  await expect(bubble(page)).toHaveText('답을 꼼꼼히 읽고 있어')
  await shot(page, `wait-00s-${test.info().project.name}`)
  await expect(page.locator('.sw-wait-glass')).toHaveCount(1)
  await expect(page.locator('.sw-wait-book')).toHaveCount(0)
  // 늘: 숨쉬기·눈 깜빡임. 0초~: 돋보기를 눈앞에 대고 훑기, 렌즈 안 큰 눈
  expect(await anim(page, '.sw-wait-breath')).toBe('sw-wait-breath')
  expect(await anim(page, '.sw-wait .st-friend-art > circle[r="10"]')).toBe('sw-wait-blink')
  expect(await anim(page, '.sw-wait-glass')).toBe('sw-wait-sweep')
  await expect(page.locator('.sw-wait-glass .sw-wait-bigeye')).toHaveCount(1)
  await page.clock.fastForward(5_000)
  await expect(bubble(page)).toHaveText('생각의 단서를 찾는 중이야')
  // 5초~ 공책 넘기기: 돋보기는 내려놓고 공책 책장이 넘어간다
  await expect(wait).toHaveAttribute('data-motion', 'notebook')
  await expect(page.locator('.sw-wait-book')).toBeVisible()
  await expect(page.locator('.sw-wait-glass')).toHaveCount(0)
  expect(await anim(page, '.sw-wait-page')).toBe('sw-wait-page')
  expect(await anim(page, '.sw-wait-pose')).toBe('sw-wait-follow')
  await shot(page, `wait-05s-${test.info().project.name}`)
  await page.clock.fastForward(10_000)
  await expect(bubble(page)).toHaveText('너에게 할 질문을 고르고 있어')
  await expect(wait).toHaveAttribute('data-motion', 'tilt')
  await expect(page.locator('.sw-wait-book')).toHaveCount(0)
  await expect(page.locator('.sw-wait-glass')).toHaveCount(1)
  // 15초~: 갸웃 + 머리 위 "?", 돋보기는 쉬는 자리(큰 눈 없음)
  expect(await anim(page, '.sw-wait-pose')).toBe('sw-wait-tilt')
  expect(await anim(page, '.sw-wait-q')).toBe('sw-wait-q')
  await expect(page.locator('.sw-wait-glass .sw-wait-bigeye')).toHaveCount(0)
  await shot(page, `wait-15s-${test.info().project.name}`)
  await page.clock.fastForward(15_000)
  await expect(bubble(page)).toHaveText('조금 오래 걸리네. 답은 벌써 저장했어!')
  await expect(wait).toHaveAttribute('data-motion', 'hop')
  expect(await anim(page, '.sw-wait-pose')).toBe('sw-wait-hop')
  await expect(page.locator('.sw-wait-q')).toHaveCount(0)
  await shot(page, `wait-30s-${test.info().project.name}`)
  // 친구를 키보드로 누르면 말풍선이 잠깐 바뀌고 한 번 콩
  const friend = page.getByRole('button', { name: /에게 말 걸기$/ })
  await friend.focus()
  await page.keyboard.press('Enter')
  await expect(bubble(page)).toHaveText('조금만 기다려 줘!')
  await expect(page.locator('.sw-wait-poke[data-poked]')).toHaveCount(1)
  await page.clock.fastForward(2_100)
  await expect(bubble(page)).toHaveText('조금 오래 걸리네. 답은 벌써 저장했어!')
  await page.keyboard.press('Space')
  await expect(bubble(page)).toHaveText('조금만 기다려 줘!')
  // 40초가 되면 결과: 대기 표시는 사라지고 같은 상자에 결과, 그 위에 "찾았다!"가 잠깐
  await page.clock.fastForward(8_000)
  await expect(wait).toHaveCount(0)
  await expect(box(page).locator('h2')).not.toHaveText('피드백을 만드는 중이에요')
  await expect(page.locator('.sw-found')).toBeVisible()
  await expect(page.locator('.sw-found')).toHaveAttribute('aria-hidden', 'true')
  // 렌즈 반짝
  expect(await anim(page, '.sw-found-glint')).toBe('sw-found-glint')
  await page.clock.fastForward(700)
  await expect(page.locator('.sw-found')).toHaveCount(0)
})

test('피드백 실패: 대기 표시가 사라지고 기존 실패 안내·"피드백 다시 받기", 다시 받으면 대기 뒤 결과', async ({ page }) => {
  await login(page)
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'ai-fail')
  await writeAndSend(page)
  const retry = page.getByRole('button', { name: '피드백 다시 받기', exact: true })
  await expect(retry).toBeVisible()
  await expect(page.locator('.sw-wait')).toHaveCount(0)
  await expect(box(page).locator('h2')).toHaveText('답은 저장했어요. 피드백은 잠시 뒤에 다시 볼 수 있어요.')
  await scenario(page, 'feedback-slow')
  await retry.click()
  await expect(page.locator('.sw-wait')).toBeVisible()
  await expect(retry).toHaveCount(0)
  // 다시 받기는 누른 시각부터 센다
  await expect(bubble(page)).toHaveText('답을 꼼꼼히 읽고 있어')
})

test('새로고침 뒤 RUNNING 이어받기: 마지막 답을 보낸 시각부터 세어 대기 표시', async ({ page }) => {
  await page.clock.install()
  await login(page)
  await scenario(page, 'feedback-slow')
  const attemptId = await openAttempt(page, { seconds: 20 })
  await go(page, attemptId)
  await expect(page.locator('.sw-wait')).toBeVisible()
  await expect(bubble(page)).toHaveText('너에게 할 질문을 고르고 있어')
  await expect(page.locator('.sw-wait')).toHaveAttribute('data-motion', 'tilt')
  await page.clock.fastForward(10_000)
  await expect(bubble(page)).toHaveText('조금 오래 걸리네. 답은 벌써 저장했어!')
})

test('새로고침 뒤 보낸 지 65초 된 RUNNING은 60초 단계부터', async ({ page }) => {
  await login(page)
  await scenario(page, 'feedback-slow')
  const attemptId = await openAttempt(page, { seconds: 65 })
  await go(page, attemptId)
  await expect(bubble(page)).toHaveText('거의 다 왔어. 잠깐만 기다려 줘')
  await expect(page.locator('.sw-wait')).toHaveAttribute('data-motion', 'hop')
  await shot(page, `resume-65s-${test.info().project.name}`)
})

for (const accessory of [false, true])
  test(`1440·768·390px에서 겹침 없음(소품 ${accessory ? '있음' : '없음'})`, async ({ page }) => {
    // 겹침은 움직이지 않는 자리에서 잰다(돋보기는 몸 쪽으로만 움직임)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    // 소품 있음은 손전등(돋보기 소품은 그려 넣는 돋보기를 빼므로 아래 따로 시험)
    await login(page, accessory ? 'ACC_LIGHT' : undefined)
    const attemptId = await openAttempt(page)
    await go(page, attemptId)
    await scenario(page, 'feedback-slow')
    await writeAndSend(page)
    await expect(page.locator('.sw-wait')).toBeVisible()
    const glass = page.locator('.sw-wait-glass')
    await expect(glass).toHaveAttribute('data-side', accessory ? 'left' : 'right')
    if (accessory) await expect(page.locator('.sw-wait image[data-slot="ACCESSORY"]')).toBeVisible()
    for (const [width, height] of [[1440, 900], [768, 1024], [390, 844]]) {
      await page.setViewportSize({ width, height })
      await page.locator('.sw-wait').scrollIntoViewIfNeeded()
      const r = await page.evaluate(() => {
        const rect = (s: string) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom } }
        return {
          glass: rect('.sw-wait-glass'), bubble: rect('.sw-wait-bubble'), panel: rect('.sw-feedback-panel'),
          acc: rect('.sw-wait image[data-slot="ACCESSORY"]'), friend: rect('.sw-wait-friend'),
          head: rect('.sw-feedback-head h2'),
          scroll: document.documentElement.scrollWidth > innerWidth,
        }
      })
      const hit = (a: typeof r.glass, b: typeof r.glass) => !!a && !!b && a.l < b.r - 1 && b.l < a.r - 1 && a.t < b.b - 1 && b.t < a.b - 1
      expect(r.scroll, `${width}px 가로 스크롤`).toBe(false)
      expect(hit(r.glass, r.bubble), `${width}px 돋보기·말풍선`).toBe(false)
      expect(hit(r.glass, r.acc), `${width}px 돋보기·소품`).toBe(false)
      expect(hit(r.friend, r.bubble), `${width}px 친구·말풍선`).toBe(false)
      expect(hit(r.head, r.friend), `${width}px 제목·친구`).toBe(false)
      for (const part of [r.glass, r.bubble, r.friend]) {
        expect(part!.l, `${width}px 패널 왼쪽 안`).toBeGreaterThanOrEqual(r.panel!.l)
        expect(part!.r, `${width}px 패널 오른쪽 안`).toBeLessThanOrEqual(r.panel!.r)
      }
      await page.locator('.sw-feedback-panel').screenshot({ path: path.join(shots, `847-layout-${width}-${accessory ? 'acc' : 'plain'}-${test.info().project.name}.png`) })
    }
  })

test('돋보기 소품을 입으면 그려 넣는 돋보기는 빼고(하나만 보임) 살피기 단계에서 입은 돋보기가 움직인다', async ({ page }) => {
  await page.clock.install()
  await login(page, 'ACC_LENS')
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  const wait = page.locator('.sw-wait')
  await expect(wait).toBeVisible()
  await expect(wait).toHaveAttribute('data-own-lens', 'true')
  await expect(page.locator('.sw-wait-glass')).toHaveCount(0)
  const lens = page.locator('.sw-wait image[data-slot="ACCESSORY"]')
  await expect(lens).toHaveCount(1)
  await expect(lens).toHaveAttribute('href', '/student-assets/looks/acc-lens.svg')
  const animation = () => lens.evaluate(e => getComputedStyle(e).animationName)
  expect(await animation()).toBe('sw-wait-own-lens')
  await page.locator('.sw-wait').scrollIntoViewIfNeeded()
  await shot(page, `own-lens-${test.info().project.name}`)
  // 움직임 줄이기면 입은 돋보기도 멈춘다
  await page.emulateMedia({ reducedMotion: 'reduce' })
  expect(await animation()).toBe('none')
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  expect(await animation()).toBe('sw-wait-own-lens')
  // 갸웃(15초~)부터는 친구 전체가 움직이고 입은 돋보기만 따로 움직이지 않는다
  await page.clock.fastForward(15_000)
  await expect(wait).toHaveAttribute('data-motion', 'tilt')
  expect(await animation()).toBe('none')
})

test('움직임 줄이기: 멈춘 그림 + 문구, 눌러도 뛰지 않고 말만 바뀜, "찾았다!" 없음', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.clock.install()
  await login(page)
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  await expect(bubble(page)).toHaveText('답을 꼼꼼히 읽고 있어')
  const still = () => page.evaluate(() => [...document.querySelectorAll('.sw-wait-glass, .sw-wait-pose, .sw-wait-poke, .sw-wait-page, .sw-wait-breath, .sw-wait-q, .sw-wait .st-friend-art > circle')]
    .map(e => { const s = getComputedStyle(e); return `${s.animationName}|${s.transform}` }))
  expect(new Set(await still())).toEqual(new Set(['none|none']))
  // 5초(공책: 펼친 공책이 멈춘 그림)·15초·30초 단계 모두 멈춤
  for (const seconds of [5_000, 10_000, 15_000]) {
    await page.clock.fastForward(seconds)
    if (seconds === 5_000) {
      await expect(page.locator('.sw-wait-book')).toBeVisible()
      await shot(page, `reduced-motion-notebook-${test.info().project.name}`)
    }
    expect(new Set(await still())).toEqual(new Set(['none|none']))
  }
  await expect(bubble(page)).toHaveText('조금 오래 걸리네. 답은 벌써 저장했어!')
  await page.getByRole('button', { name: /에게 말 걸기$/ }).click()
  await expect(bubble(page)).toHaveText('조금만 기다려 줘!')
  expect(new Set(await still())).toEqual(new Set(['none|none']))
  await shot(page, `reduced-motion-${test.info().project.name}`)
  await page.clock.fastForward(11_000)
  await expect(page.locator('.sw-wait')).toHaveCount(0)
  await expect(page.locator('.sw-found')).toBeHidden()
})

test('공책 넘기기 단계 1440·768·390px: 공책이 패널 안에 있고 말풍선·손전등과 겹치지 않음, 캡처', async ({ page }) => {
  test.skip(test.info().project.name !== 'laptop', '창 크기를 시험 안에서 바꾸므로 한 프로젝트에서만')
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.clock.install()
  await login(page, 'ACC_LIGHT')
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  await expect(page.locator('.sw-wait')).toBeVisible()
  await page.clock.fastForward(5_000)
  await expect(page.locator('.sw-wait-book')).toBeVisible()
  for (const [width, height] of [[1440, 900], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height })
    await page.locator('.sw-wait').scrollIntoViewIfNeeded()
    const r = await page.evaluate(() => {
      const rect = (s: string) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom } }
      return { book: rect('.sw-wait-book'), bubble: rect('.sw-wait-bubble'), panel: rect('.sw-feedback-panel'),
        acc: rect('.sw-wait image[data-slot="ACCESSORY"]'), scroll: document.documentElement.scrollWidth > innerWidth }
    })
    const hit = (a: typeof r.book, b: typeof r.book) => !!a && !!b && a.l < b.r - 1 && b.l < a.r - 1 && a.t < b.b - 1 && b.t < a.b - 1
    expect(r.scroll, `${width}px 가로 스크롤`).toBe(false)
    expect(hit(r.book, r.bubble), `${width}px 공책·말풍선`).toBe(false)
    expect(hit(r.book, r.acc), `${width}px 공책·손전등`).toBe(false)
    expect(r.book!.l).toBeGreaterThanOrEqual(r.panel!.l)
    expect(r.book!.r).toBeLessThanOrEqual(r.panel!.r)
    await page.locator('.sw-feedback-panel').screenshot({ path: path.join(shots, `847-notebook-${width}.png`) })
  }
})

/** 대기 모양 재기: 제목 줄 수, 말풍선 줄 수, 상자 아래 빈 공간, 상자 테두리·바탕 */
const measure = (page: Page) => page.evaluate(() => {
  const q = (s: string) => document.querySelector(s) as HTMLElement | null
  const lines = (e: HTMLElement | null) => e ? Math.round(e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight)) : -1
  const panel = q('.sw-feedback-panel')!, ps = getComputedStyle(panel)
  const content = [q('.sw-wait-friend'), q('.sw-wait-bubble'), q('.sw-wait-motion')].filter(Boolean).map(e => e!.getBoundingClientRect().bottom)
  return {
    title: lines(q('.sw-feedback-head h2')), bubble: lines(q('.sw-wait-bubble p')),
    below: Math.round(panel.getBoundingClientRect().bottom - Math.max(...content)),
    border: ps.borderTopColor, background: ps.backgroundColor, shadow: ps.boxShadow, height: Math.round(panel.getBoundingClientRect().height),
  }
})

test('대기 모양: 상자 테두리·바탕 없음, 390px 제목 한 줄, 문구마다 말풍선 2줄 이하, 아래 빈 공간, 결과가 오면 같은 상자', async ({ page }) => {
  test.skip(test.info().project.name !== 'laptop', '창 크기를 시험 안에서 바꾸므로 한 프로젝트에서만')
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.clock.install()
  await login(page)
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  await expect(page.locator('.sw-wait')).toBeVisible()
  const report: string[] = []
  let waitingHeight = 0
  for (const [at, step] of [[0, 0], [5_000, 5], [10_000, 15], [15_000, 30]] as const) {
    if (at) await page.clock.fastForward(at)
    await expect(page.locator('.sw-wait')).toHaveAttribute('data-step', String([0, 5, 15, 30].indexOf(step)))
    for (const [width, height] of [[1440, 900], [768, 1024], [390, 844]]) {
      await page.setViewportSize({ width, height })
      const m = await measure(page)
      report.push(`${step}s ${width}px 제목 ${m.title}줄 말풍선 ${m.bubble}줄 아래 ${m.below}px 높이 ${m.height}px`)
      expect(m.bubble, `${step}s ${width}px 말풍선 줄 수`).toBeLessThanOrEqual(2)
      if (width === 390) expect(m.title, '390px 제목 한 줄').toBe(1)
      expect(m.border, '대기 중 테두리 없음').toBe('rgba(0, 0, 0, 0)')
      expect(m.background, '대기 중 바탕 없음').toBe('rgba(0, 0, 0, 0)')
      expect(m.shadow).toBe('none')
      // 상자 아래 빈 공간: 체크박스 아래로 여백(390px 16px·넓은 화면 22px)과 투명 테두리(3px)만 남는다
      expect(m.below, `${step}s ${width}px 아래 빈 공간`).toBeLessThanOrEqual(26)
      if (width === 1440 && step === 30) waitingHeight = m.height
      if (step === 0 || step === 5) await page.locator('.sw-feedback-panel').screenshot({ path: path.join(shots, `847-wait-${step}s-${width}.png`) })
    }
  }
  // 친구를 누른 말도 390px에서 2줄 이하
  await page.getByRole('button', { name: /에게 말 걸기$/ }).click()
  expect((await measure(page)).bubble).toBeLessThanOrEqual(2)
  // 결과: 같은 상자(읽기 영역 하나)에 테두리·바탕이 돌아오고 높이 변화를 기록
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.clock.fastForward(11_000)
  await expect(page.locator('.sw-wait')).toHaveCount(0)
  await expect(page.locator('.ux-feedback[role=status]')).toHaveCount(1)
  const done = await measure(page)
  expect(done.border).not.toBe('rgba(0, 0, 0, 0)')
  expect(done.background).not.toBe('rgba(0, 0, 0, 0)')
  report.push(`결과 1440px 높이 ${done.height}px (대기 30초 ${waitingHeight}px, 차이 ${done.height - waitingHeight}px)`)
  await page.locator('.sw-feedback-panel').screenshot({ path: path.join(shots, '847-result-1440.png') })
  test.info().annotations.push({ type: 'measure', description: report.join('\n') })
  console.log(report.join('\n'))
})

test('화면 안 "움직임 줄이기"(WCAG 2.2.2): 기본은 OS 설정, 체크하면 모든 움직임 멈춤·문구는 바뀜, 키보드 조작, 390px 겹침 없음', async ({ page }) => {
  await page.clock.install()
  await login(page)
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  const toggle = page.getByRole('checkbox', { name: '움직임 줄이기', exact: true })
  await expect(toggle).toBeVisible()
  await expect(toggle).not.toBeChecked()
  // 읽기 영역(피드백 상자) 밖: 대기 표시가 들어올 때 체크박스 이름까지 읽히지 않게
  await expect(page.locator('.ux-feedback .sw-wait-motion')).toHaveCount(0)
  expect(await anim(page, '.sw-wait-glass')).toBe('sw-wait-sweep')
  const moving = () => page.evaluate(() => [...document.querySelectorAll('.sw-wait-glass, .sw-wait-pose, .sw-wait-poke, .sw-wait-page, .sw-wait-breath, .sw-wait-q, .sw-wait .st-friend-art > circle, .sw-wait image')]
    .map(e => getComputedStyle(e)).filter(s => s.animationName !== 'none' || s.transform !== 'none').length)
  // 키보드(Space)로 체크
  await toggle.focus()
  await page.keyboard.press('Space')
  await expect(toggle).toBeChecked()
  await expect(page.locator('.sw-wait')).toHaveAttribute('data-reduce', 'true')
  expect(await moving()).toBe(0)
  await expect(page.locator('.sw-wait-glass .sw-wait-bigeye')).toHaveCount(1)
  // 문구는 그대로 바뀌고, 단계마다 멈춘 그림
  for (const [ms, line] of [[5_000, '생각의 단서를 찾는 중이야'], [10_000, '너에게 할 질문을 고르고 있어'], [15_000, '조금 오래 걸리네. 답은 벌써 저장했어!']] as const) {
    await page.clock.fastForward(ms)
    await expect(bubble(page)).toHaveText(line)
    expect(await moving(), line).toBe(0)
  }
  // 친구를 눌러도 뛰지 않고 말만 바뀜
  await page.getByRole('button', { name: /에게 말 걸기$/ }).click()
  await expect(bubble(page)).toHaveText('조금만 기다려 줘!')
  expect(await moving()).toBe(0)
  // 390px: 체크박스가 패널 안, 말풍선·친구와 겹치지 않음
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('.sw-wait-motion').scrollIntoViewIfNeeded()
  const r = await page.evaluate(() => {
    const rect = (s: string) => { const b = document.querySelector(s)!.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom } }
    return { box: rect('.sw-wait-motion'), bubble: rect('.sw-wait-bubble'), friend: rect('.sw-wait-friend'), panel: rect('.sw-feedback-panel'),
      scroll: document.documentElement.scrollWidth > innerWidth }
  })
  const hit = (a: typeof r.box, b: typeof r.box) => a.l < b.r - 1 && b.l < a.r - 1 && a.t < b.b - 1 && b.t < a.b - 1
  expect(hit(r.box, r.bubble)).toBe(false)
  expect(hit(r.box, r.friend)).toBe(false)
  expect(r.box.r).toBeLessThanOrEqual(r.panel.r)
  expect(r.box.l).toBeGreaterThanOrEqual(r.panel.l)
  expect(r.scroll).toBe(false)
  await page.locator('.sw-feedback-panel').screenshot({ path: path.join(shots, `847-motion-off-390-${test.info().project.name}.png`) })
  // 다시 풀면 움직임이 돌아온다
  await toggle.click()
  await expect(toggle).not.toBeChecked()
  expect(await anim(page, '.sw-wait-pose')).toBe('sw-wait-hop')
})

test('OS가 움직임 줄이기면 체크박스가 처음부터 체크되어 있고 풀 수 없다(MissionScene과 같음)', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await login(page)
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  const toggle = page.getByRole('checkbox', { name: '움직임 줄이기', exact: true })
  await expect(toggle).toBeChecked()
  await toggle.click()
  await expect(toggle).toBeChecked()
  await expect(page.locator('.sw-wait')).toHaveAttribute('data-reduce', 'true')
})

test('390px 대기 화면 캡처 @responsive', async ({ page }) => {
  test.skip(test.info().project.name !== 'compact', '390px 캡처만')
  await page.clock.install()
  await login(page)
  const attemptId = await openAttempt(page)
  await go(page, attemptId)
  await scenario(page, 'feedback-slow')
  await writeAndSend(page)
  await expect(bubble(page)).toHaveText('답을 꼼꼼히 읽고 있어')
  await page.locator('.sw-wait').scrollIntoViewIfNeeded()
  await shot(page, 'wait-390')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})
