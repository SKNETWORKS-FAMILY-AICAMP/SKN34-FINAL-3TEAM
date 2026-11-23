/**
 * #885 실서버 UX 점검(NFR-UX-01·02) 1회 실행 기록. CI·tests/e2e에 넣지 않는다(사용자 결정 2026-11-22 B3).
 * 수행 구분: 모의(대역 compose — Google·LLM·M2·설명 sLLM·토스 대역, core·learning·report·DB·브로커 실제). 오류·진행 글의 "통신 끊김·늦음"만 page.route 가로채기.
 *
 * 점검
 * - 넘침(UX-01): 학부모·관리자 화면 1440·768·390, document.documentElement.scrollWidth > innerWidth (기존 MSW 시험과 같은 식)
 * - axe-core(UX-02): wcag2a·wcag2aa·wcag21a·wcag21aa·wcag22aa 위반(규칙·영향도·건수·선택자). best-practice는 참고로 건수만
 * - 키보드: 화면 첫 Tab 15회(역할·이름·초점 표시 여부), 대화 창 Esc 복귀는 별도 단계
 * - 터치 대상: 보이는 조작 요소 24px 미만(WCAG 2.5.8)·44px 미만 수, 390은 hasTouch 컨텍스트
 * - 입력 이름·현재 선택: 이름 없는 입력 수, aria-current·aria-selected·aria-pressed·checked 수
 * - 색 외 상태: 글·aria 이름 없는 상태 표시(점·배지) 후보
 *
 * 실행(저장소 루트, testing-ci 2절 compose 스택이 떠 있고 npm run test:e2e를 한 번 돌린 뒤):
 *   cd frontend/web
 *   NODE_PATH=$PWD/node_modules AXE_PATH=<저장소 밖에 받은 axe-core 4.10.2 axe.min.js> OUT_DIR=../../docs/report/evidence/issue885-ux-real-server \
 *     npx playwright test -c <playwright.e2e.config.ts를 펼치고 testDir만 이 폴더로 바꾼 설정>
 * 결과: OUT_DIR/overflow.json·axe.json·keyboard.json·states.json(axe html·failureSummary, 학생 닉네임·답 글 없음)
 */
import { expect, test, type Browser, type BrowserContext, type BrowserContextOptions, type Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { admin, newParent, useGoogleIdentity as signInWithGoogle, type GoogleIdentity } from '../../../../frontend/web/tests/e2e/support/google.ts'
import { onboardParent } from '../../../../frontend/web/tests/e2e/support/onboarding.ts'
import { solveNarrative, startExtraMission } from '../../../../frontend/web/tests/e2e/support/student.ts'
import { queueReport } from '../../../../frontend/web/tests/e2e/support/db.ts'

const AXE = process.env.AXE_PATH!
const OUT = process.env.OUT_DIR ?? '.'
const BASE = 'http://127.0.0.1:5272' // playwright.e2e.config.ts origin
const mission = '쉬는 시간을 늘린다면?' // demo_missions.sql 2번(초3 서술, 추가 문제)
const NOTI = /\/api\/v1\/notifications\?/ // 목록만(실시간 /notifications/stream 제외)
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const secrets: string[] = [] // 결과에서 지울 합성 닉네임

type Role = 'public' | 'parent' | 'admin' | 'student'
const overflow: unknown[] = [], axe: unknown[] = [], keyboard: unknown[] = [], states: unknown[] = []

// ---------- 화면 이동·기다리기 ----------
/** 화면 안 이동(학생·관리자 토큰은 메모리에만 있어 새로 고침 없이 라우터로 이동) */
async function go(page: Page, path: string) {
  await page.evaluate((p) => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')) }, path)
  await settle(page)
}
async function settle(page: Page) {
  await page.waitForTimeout(700)
  await expect(page.getByText(/불러오고 있|불러오는 중/).first()).toHaveCount(0, { timeout: 15_000 }).catch(() => {})
  await page.waitForTimeout(300)
}

// ---------- 측정 ----------
async function measureOverflow(page: Page, role: Role, screen: string, width: number) {
  await page.setViewportSize({ width, height: width >= 1024 ? 900 : width >= 768 ? 1024 : 844 })
  await page.waitForTimeout(500)
  const r = await page.evaluate(() => {
    const iw = innerWidth
    const wide = [...document.querySelectorAll('body *')].flatMap((e) => {
      const b = e.getBoundingClientRect()
      if (b.width === 0 || b.right <= iw + 1) return []
      const st = getComputedStyle(e)
      if (st.position === 'fixed' || st.visibility === 'hidden') return []
      const cls = typeof e.className === 'string' ? e.className.trim().split(/\s+/).slice(0, 2).join('.') : ''
      return [{ el: `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}${cls ? '.' + cls : ''}`, right: Math.round(b.right), width: Math.round(b.width) }]
    })
    return { scrollWidth: document.documentElement.scrollWidth, innerWidth: iw, overflow: document.documentElement.scrollWidth > iw, widest: wide.sort((a, b) => b.right - a.right).slice(0, 5) }
  })
  overflow.push({ role, screen, width, ...r })
  return r
}

async function runAxe(page: Page, role: Role, screen: string, width: number) {
  if (!(await page.evaluate(() => 'axe' in window))) await page.addScriptTag({ path: AXE })
  const res = await page.evaluate(async (tags) => {
    // @ts-expect-error axe는 주입된 전역
    const w = await window.axe.run(document, { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations'] })
    // @ts-expect-error axe는 주입된 전역
    const bp = await window.axe.run(document, { runOnly: { type: 'tag', values: ['best-practice'] }, resultTypes: ['violations'] })
    const pick = (v: { id: string; impact: string; nodes: { target: string[] }[] }) => ({ id: v.id, impact: v.impact, count: v.nodes.length, targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')) })
    return { violations: w.violations.map(pick), bestPractice: bp.violations.map((v: { id: string; impact: string; nodes: unknown[] }) => ({ id: v.id, impact: v.impact, count: v.nodes.length })) }
  }, TAGS)
  axe.push({ role, screen, width, ...res })
  return res
}

/** 첫 Tab 15회: 역할·이름(앞 30자)·초점 표시. 이름은 학생 글이 섞일 수 있어 결과 저장 때 닉네임을 지운다 */
async function tabWalk(page: Page, role: Role, screen: string, width: number) {
  // Tab 시작점을 문서 맨 앞으로: body 맨 앞에 잠깐 둔 요소에 초점을 줬다가 지운다(blur만 하면 Chrome은 마지막 초점·누른 자리에서 이어감)
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0)
    const start = document.createElement('div'); start.tabIndex = -1; document.body.prepend(start); start.focus(); start.remove()
  })
  const stops: { tag: string; role: string; name: string; visible: boolean; indicator: boolean }[] = []
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press('Tab')
    stops.push(await page.evaluate(() => {
      const e = document.activeElement as HTMLElement | null
      if (!e || e === document.body) return { tag: 'body', role: '', name: '', visible: false, indicator: false }
      const b = e.getBoundingClientRect()
      // 초점 표시: 초점 있을 때와 뺐을 때 외곽선·그림자·테두리·배경·글자색·밑줄 차이(40절과 같은 방식). 다시 초점을 줘 Tab 순서를 잇는다
      const snap = () => { const s = getComputedStyle(e); return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.borderColor, s.backgroundColor, s.color, s.textDecorationLine].join('|') }
      const on = snap()
      e.blur()
      const off = snap()
      e.focus({ preventScroll: true })
      const indicator = on !== off
      const name = (e.getAttribute('aria-label') ?? e.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 30)
      return { tag: e.tagName.toLowerCase(), role: e.getAttribute('role') ?? '', name, visible: b.width > 0 && b.height > 0, indicator }
    }))
  }
  const skip = stops.slice(0, 3).some((s) => /본문|건너뛰/.test(s.name))
  const r = { role, screen, width, skipLink: skip, stops: stops.length, noIndicator: stops.filter((s) => s.tag !== 'body' && !s.indicator).length,
    hidden: stops.filter((s) => s.tag !== 'body' && !s.visible).length, bodyStops: stops.filter((s) => s.tag === 'body').length, order: stops }
  keyboard.push(r)
  return r
}

/** 터치 대상 크기·이름 없는 입력·현재 선택 표시·색만으로 보일 수 있는 상태 후보 */
async function pageStates(page: Page, role: Role, screen: string, width: number) {
  const r = await page.evaluate(() => {
    const visible = (e: Element) => { const b = e.getBoundingClientRect(); const st = getComputedStyle(e); return b.width > 0 && b.height > 0 && st.visibility !== 'hidden' && st.display !== 'none' }
    const controls = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=radio], [role=checkbox], [role=switch], [role=link]')]
      .filter((e) => visible(e) && !(e as HTMLButtonElement).disabled && e.getAttribute('aria-hidden') !== 'true' && !e.closest('[aria-hidden="true"]'))
    const size = (e: Element) => { const b = e.getBoundingClientRect(); return Math.min(b.width, b.height) }
    // 글 안의 링크(문장 속 a)는 WCAG 2.5.8 예외라 따로 센다
    const inline = (e: Element) => e.tagName === 'A' && getComputedStyle(e).display === 'inline'
    const small24 = controls.filter((e) => size(e) < 24 && !inline(e))
    const small44 = controls.filter((e) => size(e) < 44 && !inline(e))
    const desc = (e: Element) => { const cls = typeof e.className === 'string' ? e.className.trim().split(/\s+/).slice(0, 2).join('.') : ''; return `${e.tagName.toLowerCase()}${cls ? '.' + cls : ''}[${Math.round(e.getBoundingClientRect().width)}x${Math.round(e.getBoundingClientRect().height)}] ${(e.getAttribute('aria-label') ?? e.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 20)}` }
    const inputs = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(visible)
    const unnamed = inputs.filter((e) => {
      const i = e as HTMLInputElement
      return !(i.labels?.length || i.getAttribute('aria-label') || i.getAttribute('aria-labelledby') || i.getAttribute('title'))
    })
    const stateLike = [...document.querySelectorAll('[class*="status"], [class*="badge"], [class*="dot"], [class*="chip"], [class*="pill"], [class*="state"]')].filter(visible)
    const colorOnly = stateLike.filter((e) => !(e.textContent ?? '').trim() && !e.getAttribute('aria-label') && !e.getAttribute('title') && e.getAttribute('aria-hidden') !== 'true' && !e.closest('[aria-hidden="true"]') && !e.querySelector('svg, img'))
    return {
      pointerCoarse: matchMedia('(pointer: coarse)').matches,
      controls: controls.length, under24: small24.length, under44: small44.length, under24List: small24.slice(0, 8).map(desc), under44List: small44.slice(0, 8).map(desc),
      inputs: inputs.length, unnamedInputs: unnamed.length, unnamedList: unnamed.slice(0, 5).map(desc),
      selection: { ariaCurrent: document.querySelectorAll('[aria-current]:not([aria-current="false"])').length, ariaSelected: document.querySelectorAll('[aria-selected="true"]').length,
        ariaPressed: document.querySelectorAll('[aria-pressed="true"]').length, checked: document.querySelectorAll('input:checked').length },
      liveRegions: { status: document.querySelectorAll('[role=status]').length, alert: document.querySelectorAll('[role=alert]').length },
      colorOnlyCandidates: colorOnly.slice(0, 8).map(desc),
    }
  })
  states.push({ role, screen, width, ...r })
  return r
}

/** 부가 단계(오류 글·상세 화면 등)는 실패해도 기록만 하고 다음 점검으로 넘어간다 */
async function step(name: string, extra: Record<string, unknown>, run: () => Promise<void>) {
  try { await run() } catch (e) { extra[`${name}Error`] = String((e as Error).message ?? e).split(/\r?\n/)[0].slice(0, 200) }
}
async function a11y(page: Page, role: Role, screen: string, width: number) {
  await runAxe(page, role, screen, width)
  await tabWalk(page, role, screen, width)
  await pageStates(page, role, screen, width)
}

// ---------- 로그인 ----------
async function googleLogin(browser: Browser, identity: GoogleIdentity, entry: '/login' | '/admin/login', done: string, options: BrowserContextOptions = {}) {
  const context = await browser.newContext({ baseURL: BASE, ...options })
  await signInWithGoogle(context, identity)
  const page = await context.newPage()
  await page.goto(entry)
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL(done)
  await settle(page)
  return { context, page }
}
/** loginStudent(support/student.ts)와 같고 컨텍스트 옵션(터치)만 받는다 */
async function pairStudent(browser: Browser, parentPage: Page, nickname: string, options: BrowserContextOptions, first: boolean) {
  await go(parentPage, '/parent/devices')
  if (first) {
    const pin = parentPage.getByRole('form', { name: `${nickname} PIN`, exact: true })
    await pin.getByLabel(`${nickname} 새 PIN`, { exact: true }).fill('4831')
    await pin.getByLabel(`${nickname} 새 PIN 확인`, { exact: true }).fill('4831')
    await pin.getByRole('button', { name: 'PIN 정하기', exact: true }).click()
    await expect(pin.getByRole('status')).toContainText('PIN을 저장했습니다.')
  }
  const pairing = parentPage.waitForResponse((r) => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/student-devices/pairings'))
  await parentPage.getByRole('button', { name: '등록 코드 만들기', exact: true }).click()
  const { pairingCode } = await (await pairing).json()
  const context = await browser.newContext({ baseURL: new URL(parentPage.url()).origin, ...options })
  const page = await context.newPage()
  await page.goto('/student/login?code=' + encodeURIComponent(pairingCode))
  await page.getByLabel('기기 이름', { exact: true }).fill(`UX 점검 ${options.hasTouch ? '터치' : 'PC'}`)
  await page.getByRole('button', { name: '이 기기 등록하기', exact: true }).click()
  return { context, page }
}
async function enterPin(page: Page) {
  for (const digit of ['4', '8', '3', '1']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await page.waitForURL('**/student/home**')
  await settle(page)
}

// ---------- 화면 목록 ----------
const PARENT_SCREENS: [string, string][] = [
  ['학습 현황', '/parent/journal'], ['리포트·AI 챗봇', '/parent/report'], ['계정·자녀 설정', '/parent/settings'], ['기기·PIN', '/parent/devices'],
  ['이용권·결제', '/parent/billing'], ['도움말', '/parent/help'], ['문의', '/parent/support'], ['문의 결과', '/parent/support/results'],
  ['공지', '/parent/notices'], ['알림', '/parent/notifications'], ['계정', '/parent/account'], ['보호자 이전', '/parent/transfers'], ['자녀 추가', '/parent/children/new'],
]
const ADMIN_SCREENS: [string, string][] = [
  ['운영 현황', '/admin/home'], ['감사 이력', '/admin/audit'], ['미션 관리', '/admin/missions'], ['미션 초안', '/admin/mission-drafts'], ['게시 관리', '/admin/themes'],
  ['주간 테마 검수', '/admin/theme-drafts'], ['꾸미기 아이템', '/admin/looks'], ['작업 재처리', '/admin/jobs'], ['작업 대기열', '/admin/queues'], ['오류 신고', '/admin/errors'],
  ['문의·공지', '/admin/support'], ['모델·프롬프트', '/admin/models'], ['표현 검토', '/admin/expressions'], ['AI 사용량', '/admin/usage'], ['결제·환불', '/admin/payments'],
]
const STUDENT_SCREENS: [string, string][] = [
  ['홈', '/student/home'], ['시작 이야기', '/student/theme/intro'], ['단서 모음', '/student/theme/clues'], ['미션 고르기', '/student/missions'], ['내 공책', '/student/journal'],
  ['생각 활동', '/student/activities'], ['내 방', '/student/room'], ['추억 앨범', '/student/album'], ['꾸미기', '/student/customize'], ['뭉치 친구들', '/student/friends'],
  ['친구 생각', '/student/community'], ['설정', '/student/settings'], ['내 포인트', '/student/points'], ['도움말', '/student/help'],
]

test('#885 실서버 UX 점검: 넘침(학부모·관리자 1440·768·390), 접근성(학생·학부모·관리자 1440·390)', async ({ browser }) => {
  test.setTimeout(3_600_000)
  const contexts: BrowserContext[] = []
  const extra: Record<string, unknown> = { run: new Date().toISOString() }
  try {
    // ---- 공개 화면(로그인 전) ----
    {
      const ctx = await browser.newContext({ baseURL: BASE }); contexts.push(ctx)
      const page = await ctx.newPage()
      await page.route(/https:\/\/(fonts\.(googleapis|gstatic)\.com|js\.tosspayments\.com)\//, (r) => r.abort())
      for (const [screen, path] of [['학부모 로그인', '/login'], ['관리자 로그인', '/admin/login']] as const) {
        await page.goto(path); await settle(page)
        for (const w of [1440, 768, 390]) await measureOverflow(page, 'public', screen, w)
        for (const w of [1440, 390]) { await page.setViewportSize({ width: w, height: 900 }); await a11y(page, 'public', screen, w) }
      }
    }

    // ---- 학부모 준비: 새 보호자 + 초3 자녀 + 미션 1개 + 주간 리포트 ----
    const parentId = newParent('ux-audit')
    const nickname = `점검${Date.now().toString(36)}`; secrets.push(nickname)
    // 새 보호자 첫 화면(온보딩 동의 단계): 따로 만든 보호자로 들어가 보기만 함
    {
      const o = await googleLogin(browser, newParent('ux-onboarding'), '/login', '**/parent/onboarding**', { viewport: { width: 1440, height: 900 } }); contexts.push(o.context)
      await a11y(o.page, 'parent', '새 보호자 온보딩(동의)', 1440)
      for (const w of [1440, 768, 390]) await measureOverflow(o.page, 'parent', '새 보호자 온보딩(동의)', w)
      await a11y(o.page, 'parent', '새 보호자 온보딩(동의)', 390)
    }
    const parentCtx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } }); contexts.push(parentCtx)
    await signInWithGoogle(parentCtx, parentId)
    const parentPage = await parentCtx.newPage()
    await onboardParent(parentPage, nickname)
    const student = await pairStudent(browser, parentPage, nickname, { viewport: { width: 1440, height: 900 } }, true); contexts.push(student.context)
    const spage = student.page
    await expect(spage.getByRole('button', { name: '4', exact: true })).toBeVisible()
    // 학생 PIN 화면(로그인 전)
    await a11y(spage, 'student', 'PIN 로그인', 1440)
    await enterPin(spage)
    // 미션 1개 마무리(포인트 10·리포트 재료)
    await startExtraMission(spage, mission)
    // 풀이 화면(답 쓰기 전) 점검
    await settle(spage)
    await a11y(spage, 'student', '풀이', 1440)
    await solveNarrative(spage, '저는 찬성이에요. 쉬는 시간에 몸을 움직이면 다음 시간에 더 집중할 수 있기 때문이에요.')
    const [from, to] = queueReport(nickname).split(' ')
    extra.reportPeriod = `${from}~${to}`

    // ---- 학부모 화면: 1440·768·390 넘침, 1440 접근성 ----
    await parentPage.route(/https:\/\/(fonts\.(googleapis|gstatic)\.com|js\.tosspayments\.com)\//, (r) => r.abort())
    for (const [screen, path] of PARENT_SCREENS) {
      await parentPage.setViewportSize({ width: 1440, height: 900 })
      await go(parentPage, path)
      await a11y(parentPage, 'parent', screen, 1440)
      for (const w of [1440, 768, 390]) await measureOverflow(parentPage, 'parent', screen, w)
    }
    // 리포트 목록·상세(생성 완료까지 기다림)
    await parentPage.setViewportSize({ width: 1440, height: 900 })
    await go(parentPage, '/parent/report')
    const card = parentPage.locator('article', { has: parentPage.getByRole('heading', { name: `${from} ~ ${to}` }) })
    await expect(async () => {
      await parentPage.reload(); await settle(parentPage)
      await parentPage.getByRole('button', { name: '리포트 자세히 보기', exact: false }).click()
      await expect(card.getByText('생성 완료')).toBeVisible({ timeout: 5_000 })
    }).toPass({ timeout: 180_000, intervals: [3_000] })
    await a11y(parentPage, 'parent', '리포트 목록(창)', 1440)
    for (const w of [1440, 768, 390]) await measureOverflow(parentPage, 'parent', '리포트 목록(창)', w)
    await parentPage.setViewportSize({ width: 1440, height: 900 })
    await card.getByRole('button', { name: '자세히 보기' }).click()
    await expect(parentPage.getByRole('heading', { name: '주간 리포트', exact: true })).toBeVisible()
    await settle(parentPage)
    await a11y(parentPage, 'parent', '주간 리포트 상세', 1440)
    for (const w of [1440, 768, 390]) await measureOverflow(parentPage, 'parent', '주간 리포트 상세', w)
    // 대화 창 Esc: 리포트 창을 Esc로 닫으면 초점이 연 단추로
    await step('parentDialog', extra, async () => {
    await parentPage.setViewportSize({ width: 1440, height: 900 })
    await go(parentPage, '/parent/report')
    const launcher = parentPage.getByRole('button', { name: '리포트 자세히 보기', exact: false })
    await launcher.click()
    await expect(parentPage.getByRole('dialog').first()).toBeVisible()
    await parentPage.keyboard.press('Escape')
    await parentPage.waitForTimeout(500)
    extra.parentDialogEsc = { closed: (await parentPage.getByRole('dialog').count()) === 0, focusBack: await launcher.evaluate((e) => e === document.activeElement) }
    })

    // ---- 오류·진행 글(학부모): 늦게 오면 진행 글, 끊기면 오류 글 ----
    await step('parentProgress', extra, async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((r) => { release = r })
      await parentPage.route(NOTI, async (route) => { await gate; await route.continue().catch(() => {}) })
      await go(parentPage, '/parent/notifications').catch(() => {})
      await parentPage.waitForTimeout(800)
      const loading = await parentPage.locator('[role=status]').allTextContents()
      release()
      await parentPage.unroute(NOTI)
      await parentPage.route(NOTI, (route) => route.abort('internetdisconnected').catch(() => {}))
      await go(parentPage, '/parent/journal'); await go(parentPage, '/parent/notifications')
      await parentPage.waitForTimeout(1500)
      const failed = await parentPage.locator('[role=alert]').allTextContents()
      await parentPage.unroute(NOTI)
      extra.parentProgressError = { screen: '알림', loadingStatusTexts: loading.map((t) => t.trim()).filter(Boolean).slice(0, 3), errorAlertTexts: failed.map((t) => t.trim()).filter(Boolean).slice(0, 3) }
    })

    // ---- 학생 화면 1440 ----
    for (const [screen, path] of STUDENT_SCREENS) {
      await spage.setViewportSize({ width: 1440, height: 900 })
      await go(spage, path)
      await a11y(spage, 'student', screen, 1440)
      await measureOverflow(spage, 'student', screen, 1440)
    }
    // 내 방 › 방 꾸미기 › 방 소품(#805 색 단추): 포인트 부족 안내·사기·놓기·색 단추 키보드
    await step('decor', extra, async () => {
      await go(spage, '/student/room')
      await spage.getByRole('button', { name: '방 꾸미기', exact: true }).click()
      const drawer = spage.getByRole('region', { name: '방 꾸미기' })
      await drawer.getByRole('button', { name: '방 소품', exact: true }).click()
      await settle(spage)
      await a11y(spage, 'student', '내 방 서랍(방 소품)', 1440)
      const card = drawer.locator('.st-decor-card').filter({ hasText: 'E2E 작은 화분' })
      const buy = card.getByRole('button', { name: /E2E 작은 화분 1개 사기/ })
      const points = await drawer.locator('.st-room-points').textContent()
      await buy.click()
      const confirm = drawer.locator('section[aria-label="방 소품 사기 확인"]')
      await expect(confirm).toBeVisible()
      const confirmText = (await confirm.textContent())?.replace(/\s+/g, ' ').trim().slice(0, 120)
      const canBuy = await confirm.getByRole('button', { name: '포인트로 사기' }).isEnabled()
      extra.decorBuy = { points, confirmText, canBuy }
      if (canBuy) {
        await confirm.getByRole('button', { name: '포인트로 사기' }).click()
        await card.getByRole('button', { name: 'E2E 작은 화분 놓기' }).click()
        const colors = drawer.getByRole('group', { name: 'E2E 작은 화분 색' })
        await expect(colors).toBeVisible()
        // 옮기기 판을 열면 초점이 화살표 첫 단추로 가는지(점검 Tab 이동 전에 확인)
        const padFirst = drawer.getByRole('button', { name: /뒤로 한 칸|위로 한 칸/ })
        const focusOnOpen = await padFirst.evaluate((e) => e === document.activeElement)
        await a11y(spage, 'student', '내 방 옮기기 판(색 단추)', 1440)
        // 색 단추 키보드: 화살표 첫 단추에서 Shift+Tab으로 마지막 색 → Space
        await padFirst.focus()
        await spage.keyboard.press('Shift+Tab')
        const lastColor = await spage.evaluate(() => document.activeElement?.getAttribute('aria-label'))
        await spage.keyboard.press('Space')
        const pressedAfter = await colors.locator('[aria-pressed="true"]').getAttribute('aria-label')
        // 방향키는 판 전체에 걸려 색 단추에 초점이 있어도 소품이 움직인다(설계 1.3 확인 동작)
        extra.decorColorKeyboard = { focusOnOpen, focusedByShiftTab: lastColor, pressedAfterSpace: pressedAfter, names: await colors.getByRole('button').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label'))) }
        await drawer.getByRole('button', { name: '다 놓았어요' }).click()
        await spage.getByRole('button', { name: '저장', exact: true }).click()
        await expect(spage.locator('.st-room-note')).toHaveText('내 방을 저장했어요.')
        // 저장 뒤 포인트 부족 상태에서 다시 사기를 누르면
        await spage.getByRole('button', { name: '방 꾸미기', exact: true }).click()
        await drawer.getByRole('button', { name: '방 소품', exact: true }).click()
        await settle(spage)
        const again = drawer.locator('.st-decor-card').filter({ hasText: 'E2E 작은 화분' }).getByRole('button', { name: /E2E 작은 화분 1개 사기/ })
        if (await again.isEnabled()) {
          await again.click()
          const c2 = drawer.locator('section[aria-label="방 소품 사기 확인"]')
          extra.decorBuyShort = { text: (await c2.textContent())?.replace(/\s+/g, ' ').trim().slice(0, 160), buyEnabled: await c2.getByRole('button', { name: '포인트로 사기' }).isEnabled() }
          await c2.getByRole('button', { name: '취소' }).click().catch(() => {})
        } else extra.decorBuyShort = { buyButtonDisabled: true }
        await spage.getByRole('button', { name: '취소', exact: true }).click()
      }
      // 통신 끊김: 놓은 칸 목록을 못 받으면 글로 안내
      await spage.route('**/students/me/room/decor-spots', (route) => (route.request().method() === 'GET' ? route.abort('internetdisconnected') : route.continue()).catch(() => {}))
      await go(spage, '/student/home'); await go(spage, '/student/room')
      await spage.getByRole('button', { name: '방 꾸미기', exact: true }).click().catch(() => {})
      await drawer.getByRole('button', { name: '방 소품', exact: true }).click().catch(() => {})
      await spage.waitForTimeout(1500)
      extra.studentDecorError = { alertTexts: (await spage.locator('[role=alert]').allTextContents()).map((t) => t.trim()).filter(Boolean).slice(0, 3) }
      await spage.unroute('**/students/me/room/decor-spots')
      await spage.getByRole('button', { name: '취소', exact: true }).click().catch(() => {})
    })

    // ---- 관리자: 1440·768·390 넘침, 1440 접근성 ----
    const a = await googleLogin(browser, admin, '/admin/login', '**/admin/home**', { viewport: { width: 1440, height: 900 } }); contexts.push(a.context)
    for (const [screen, path] of ADMIN_SCREENS) {
      await a.page.setViewportSize({ width: 1440, height: 900 })
      await go(a.page, path)
      await a11y(a.page, 'admin', screen, 1440)
      for (const w of [1440, 768, 390]) await measureOverflow(a.page, 'admin', screen, w)
    }
    // 상세 화면: 작업 상세·테마 초안 상세·미션 편집(목록 첫 줄을 열 수 있으면)
    const details: [string, string, RegExp][] = [['작업 상세', '/admin/jobs', /상세|열기|보기/], ['테마 초안 상세', '/admin/theme-drafts', /상세|열기|보기/], ['미션 편집', '/admin/missions', /편집|수정|열기/]]
    extra.adminDetails = []
    await step('adminDetails', extra, async () => { for (const [screen, path, name] of details) {
      await a.page.setViewportSize({ width: 1440, height: 900 })
      await go(a.page, path)
      const open = a.page.locator('#admin-main').getByRole('button', { name }).or(a.page.locator('#admin-main').getByRole('link', { name })).first()
      if (!(await open.count())) { (extra.adminDetails as unknown[]).push({ screen, opened: false }); continue }
      await open.click(); await settle(a.page)
      ;(extra.adminDetails as unknown[]).push({ screen, opened: true, path: new URL(a.page.url()).pathname.replace(/[0-9a-f-]{36}/g, ':id') })
      await a11y(a.page, 'admin', screen, 1440)
      for (const w of [1440, 768, 390]) await measureOverflow(a.page, 'admin', screen, w)
      await a.page.keyboard.press('Escape').catch(() => {})
    } })
    // 관리자 실서버 오류 글: 꾸미기 아이템 코드 중복(E2E_HAT) 409
    await step('adminDuplicate', extra, async () => {
      await a.page.setViewportSize({ width: 1440, height: 900 })
      await go(a.page, '/admin/looks')
      const create = a.page.locator('#admin-main').getByRole('button', { name: /새 아이템|아이템 추가|등록/ }).first()
      if (await create.count()) {
        await create.click()
        const code = a.page.getByLabel(/아이템 코드|코드/).first()
        if (await code.count()) {
          await code.fill('E2E_HAT')
          const name = a.page.getByLabel(/이름/).first(); if (await name.count()) await name.fill('UX 점검 중복')
          const res = a.page.waitForResponse((r) => new URL(r.url()).pathname.startsWith('/api/v1/admin/look-items') && r.request().method() === 'POST', { timeout: 10_000 }).catch(() => null)
          await a.page.locator('#admin-main').getByRole('button', { name: /저장|등록|만들기/ }).last().click().catch(() => {})
          const r = await res
          await a.page.waitForTimeout(800)
          extra.adminDuplicate = { status: r?.status() ?? null, alerts: (await a.page.locator('[role=alert]').allTextContents()).map((t) => t.trim()).filter(Boolean).slice(0, 3) }
        } else extra.adminDuplicate = { codeField: false }
      } else extra.adminDuplicate = { createButton: false }
    })
    // 관리자 진행·오류 글: 작업 목록 늦음·끊김
    await step('adminProgress', extra, async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((r) => { release = r })
      await a.page.route('**/api/v1/admin/jobs**', async (route) => { await gate; await route.continue().catch(() => {}) })
      await go(a.page, '/admin/home'); await go(a.page, '/admin/jobs').catch(() => {})
      const loading = await a.page.locator('[role=status]').allTextContents()
      release(); await a.page.unroute('**/api/v1/admin/jobs**')
      await a.page.route('**/api/v1/admin/jobs**', (route) => route.abort('internetdisconnected').catch(() => {}))
      await go(a.page, '/admin/home'); await go(a.page, '/admin/jobs')
      await a.page.waitForTimeout(1500)
      const failed = await a.page.locator('[role=alert]').allTextContents()
      await a.page.unroute('**/api/v1/admin/jobs**')
      extra.adminProgressError = { screen: '작업 재처리', loadingStatusTexts: loading.map((t) => t.trim()).filter(Boolean).slice(0, 3), errorAlertTexts: failed.map((t) => t.trim()).filter(Boolean).slice(0, 3) }
    })

    // ---- 390 터치(hasTouch) 접근성: 학부모·관리자·학생 ----
    const touch: BrowserContextOptions = { viewport: { width: 390, height: 844 }, hasTouch: true }
    const pt = await googleLogin(browser, parentId, '/login', '**/parent/journal**', touch); contexts.push(pt.context)
    for (const [screen, path] of PARENT_SCREENS) { await go(pt.page, path); await a11y(pt.page, 'parent', screen, 390) }
    const at = await googleLogin(browser, admin, '/admin/login', '**/admin/home**', touch); contexts.push(at.context)
    for (const [screen, path] of ADMIN_SCREENS) { await go(at.page, path); await a11y(at.page, 'admin', screen, 390) }
    const st = await pairStudent(browser, parentPage, nickname, touch, false); contexts.push(st.context)
    await expect(st.page.getByRole('button', { name: '4', exact: true })).toBeVisible()
    await a11y(st.page, 'student', 'PIN 로그인', 390)
    await enterPin(st.page)
    for (const [screen, path] of STUDENT_SCREENS) { await go(st.page, path); await a11y(st.page, 'student', screen, 390); await measureOverflow(st.page, 'student', screen, 390) }
  } finally {
    const scrub = (v: unknown) => { let s = JSON.stringify(v, null, 1); for (const n of secrets) s = s.replaceAll(n, '<자녀>'); return s + '\n' }
    writeFileSync(join(OUT, 'overflow.json'), scrub(overflow), 'utf8')
    writeFileSync(join(OUT, 'axe.json'), scrub(axe), 'utf8')
    writeFileSync(join(OUT, 'keyboard.json'), scrub(keyboard), 'utf8')
    writeFileSync(join(OUT, 'states.json'), scrub({ extra, pages: states }), 'utf8')
    for (const c of contexts) await c.close().catch(() => {})
  }
})
