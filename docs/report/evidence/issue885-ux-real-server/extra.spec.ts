/**
 * #885 추가 확인(ux-audit.spec.ts에서 빠진 두 가지, 2026-11-23). 실행 방법·환경은 ux-audit.spec.ts와 같다(같은 compose 스택·axe 파일·설정).
 * 1) 테마 초안 상세: 관리자 화면 "주간 테마 검수 › 새 테마 초안 요청"으로 초안을 만들고(POST /admin/theme-drafts → learning 주기 작업 → ai → llm-stub),
 *    상태가 GENERATING을 벗어나면 목록 "열기"로 상세를 연다. 점검은 ux-audit 관리자 화면과 같음: 넘침 1440·768·390, axe·첫 Tab 15회·입력 이름·현재 선택·색 외 상태 1440·390 터치
 * 2) 꾸미기 아이템 코드 중복 409: "새 아이템"에 시드 코드 E2E_HAT(core.sql)를 넣고 키보드(저장 단추 Enter)로 저장 → 응답 코드·오류 글(role=alert)·초점 위치
 *    상세의 대비 위반은 글자색·배경색·대비·글자 크기도 남김(supplement.spec.ts contrast와 같은 코드)
 * 결과: OUT_DIR/extra.json(overflow·axe·keyboard·states는 ux-audit와 같은 모양, contrast는 supplement.json 모양에 선택자 targets를 더함)
 * 성취기준 표: e2e-seed가 넣지 않으므로 실행 전에 저장소 시드를 넣는다(evaluation/datasets/memory@2/README.md와 같은 절차, 다시 넣으면 덮어씀). 그 밖의 DB 직접 삽입 없음
 *   docker exec -i sagomungchi-e2e-postgres-1 sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d learning_db' < backend/learning-service/db/seed/achievement_standards.sql
 * 2026-11-23 02:51 실행은 시드 전이라 1) 요청이 409(learning "자동 성취기준 없음")였고, 시드를 넣은 09:05·09:08 실행에서 초안이 생겨(ai가 OpenAI 키 없음으로 503 → 실패 초안) 상세를 엶. 결과 파일은 09:08 실행, 02:51 결과는 extra-0251.json
 */
import { expect, test, type Browser, type BrowserContext, type BrowserContextOptions, type Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { admin, useGoogleIdentity as signInWithGoogle, type GoogleIdentity } from '../../../../frontend/web/tests/e2e/support/google.ts'

const AXE = process.env.AXE_PATH!
const OUT = process.env.OUT_DIR ?? '.'
const BASE = 'http://127.0.0.1:5272'
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
type Role = 'admin'
const overflow: unknown[] = [], axe: unknown[] = [], keyboard: unknown[] = [], states: unknown[] = [], contrast: unknown[] = []

// ---------- 아래 go·settle·측정 4개·googleLogin은 ux-audit.spec.ts와 같은 코드(스펙끼리 import 불가라 복사) ----------
async function go(page: Page, path: string) {
  await page.evaluate((p) => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')) }, path)
  await settle(page)
}
async function settle(page: Page) {
  await page.waitForTimeout(700)
  await expect(page.getByText(/불러오고 있|불러오는 중/).first()).toHaveCount(0, { timeout: 15_000 }).catch(() => {})
  await page.waitForTimeout(300)
}
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
async function tabWalk(page: Page, role: Role, screen: string, width: number) {
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
async function pageStates(page: Page, role: Role, screen: string, width: number) {
  const r = await page.evaluate(() => {
    const visible = (e: Element) => { const b = e.getBoundingClientRect(); const st = getComputedStyle(e); return b.width > 0 && b.height > 0 && st.visibility !== 'hidden' && st.display !== 'none' }
    const controls = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=radio], [role=checkbox], [role=switch], [role=link]')]
      .filter((e) => visible(e) && !(e as HTMLButtonElement).disabled && e.getAttribute('aria-hidden') !== 'true' && !e.closest('[aria-hidden="true"]'))
    const size = (e: Element) => { const b = e.getBoundingClientRect(); return Math.min(b.width, b.height) }
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
async function a11y(page: Page, role: Role, screen: string, width: number) {
  await runAxe(page, role, screen, width)
  await tabWalk(page, role, screen, width)
  await pageStates(page, role, screen, width)
}
async function googleLogin(browser: Browser, identity: GoogleIdentity, entry: '/admin/login', done: string, options: BrowserContextOptions = {}) {
  const context = await browser.newContext({ baseURL: BASE, ...options })
  await signInWithGoogle(context, identity)
  const page = await context.newPage()
  await page.goto(entry)
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL(done)
  await settle(page)
  return { context, page }
}
/** supplement.spec.ts contrast와 같은 코드: 대비 위반 노드의 글자색·배경색·대비·글자 크기(묶어서 건수) */
async function contrastValues(page: Page, screen: string, width: number) {
  if (!(await page.evaluate(() => 'axe' in window))) await page.addScriptTag({ path: AXE })
  const values = await page.evaluate(async () => {
    // @ts-expect-error axe는 주입된 전역
    const r = await window.axe.run(document, { runOnly: { type: 'rule', values: ['color-contrast'] }, resultTypes: ['violations'] })
    const seen = new Map<string, { fg: string; bg: string; ratio: number; fontSize: string; fontWeight: string; expected: string; count: number; targets: string[] }>()
    for (const v of r.violations) for (const n of v.nodes) {
      const d = (n.any[0]?.data ?? {}) as { fgColor: string; bgColor: string; contrastRatio: number; fontSize: string; fontWeight: string; expectedContrastRatio: string }
      const key = `${d.fgColor}|${d.bgColor}|${d.fontSize}|${d.fontWeight}`
      const s = seen.get(key)
      if (s) { s.count++; s.targets.push(n.target.join(' ')) }
      else seen.set(key, { fg: d.fgColor, bg: d.bgColor, ratio: d.contrastRatio, fontSize: d.fontSize, fontWeight: d.fontWeight, expected: d.expectedContrastRatio, count: 1, targets: [n.target.join(' ')] })
    }
    return [...seen.values()].sort((a, b) => b.count - a.count)
  })
  contrast.push({ role: 'admin', screen, width, values })
}
// ---------- 복사 끝 ----------

/** 초점이 있는 요소 설명(태그·역할·이름 앞 30자·보임) */
const focused = (page: Page) => page.evaluate(() => {
  const e = document.activeElement as HTMLElement | null
  if (!e || e === document.body) return { tag: 'body' }
  const b = e.getBoundingClientRect()
  return { tag: e.tagName.toLowerCase(), role: e.getAttribute('role') ?? '', name: (e.getAttribute('aria-label') ?? e.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 30), inViewport: b.bottom > 0 && b.top < innerHeight }
})

/** 꾸미기 아이템 코드 중복: 새 아이템 → E2E_HAT → 저장 단추에 초점을 두고 Enter */
async function duplicateItem(page: Page, width: number) {
  await go(page, '/admin/looks')
  await page.locator('#admin-main').getByRole('button', { name: '새 아이템', exact: true }).click()
  const form = page.locator('#admin-main form').filter({ has: page.getByLabel('아이템 코드', { exact: true }) })
  await form.getByLabel('아이템 코드', { exact: true }).fill('E2E_HAT')
  await form.getByLabel('아이템 칸', { exact: true }).selectOption('HAT')
  await form.getByLabel('아이템 이름', { exact: true }).fill('UX 점검 중복')
  await form.getByLabel('필요 포인트', { exact: true }).fill('10')
  await form.getByLabel('그림 키', { exact: true }).fill('looks/hat-acorn.svg')
  const save = form.getByRole('button', { name: '저장', exact: true })
  await save.focus()
  const res = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/admin/look-items' && r.request().method() === 'POST', { timeout: 15_000 })
  await page.keyboard.press('Enter')
  const r = await res
  const body = await r.json().catch(() => ({})) as { code?: string; title?: string; status?: number }
  const alert = form.getByRole('alert')
  await expect(alert.first()).toBeVisible()
  await page.waitForTimeout(500)
  const alerts = (await alert.allTextContents()).map((t) => t.replace(/\s+/g, ' ').trim()).filter(Boolean)
  const alertBox = await alert.first().boundingBox()
  return {
    width, status: r.status(), code: body.code ?? null, problemTitle: body.title ?? null,
    alertTexts: alerts.slice(0, 3), alertVisible: await alert.first().isVisible(),
    alertInViewport: alertBox ? alertBox.y + alertBox.height > 0 && alertBox.y < (page.viewportSize()?.height ?? 0) : false,
    formStillOpen: await form.isVisible(), codeKept: await form.getByLabel('아이템 코드', { exact: true }).inputValue(),
    focusAfter: await focused(page),
    detailsToggle: await form.locator('.error-details summary').count(),
  }
}

test('#885 추가: 테마 초안 상세(1440·768·390, 390 터치)와 아이템 코드 중복 409', async ({ browser }) => {
  test.setTimeout(1_800_000)
  const contexts: BrowserContext[] = []
  const extra: Record<string, unknown> = { run: new Date().toISOString() }
  let detailPathForTouch: string | null = null // 390에서 열 상세 주소. 결과 파일에는 초안 ID를 :id로 가려 남김
  try {
    const a = await googleLogin(browser, admin, '/admin/login', '**/admin/home**', { viewport: { width: 1440, height: 900 } }); contexts.push(a.context)
    const page = a.page

    // ---- 1) 테마 초안 만들기: 화면 요청 폼 기본값(초3·다음 주 월요일·주제 비움) ----
    await go(page, '/admin/theme-drafts')
    extra.listBefore = { rows: await page.locator('#admin-main table tbody tr').count() }
    await page.locator('#admin-main summary', { hasText: '새 테마 초안 요청' }).click()
    const form = page.getByRole('form', { name: '테마 초안 생성 요청' })
    const posted = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/admin/theme-drafts' && r.request().method() === 'POST')
    await form.getByRole('button', { name: '테마 초안 생성 요청' }).click()
    const created = await posted
    if (created.status() !== 202) {
      // 2026-11-23 02:51 실행(시드 전): 성취기준 표(achievement_standard)가 비어 409 "자동 성취기준 없음" → 초안이 생기지 않아 상세는 열지 못함. 화면 오류 글만 기록하고 2)로 넘어감
      const p = await created.json().catch(() => ({})) as { code?: string; title?: string; detail?: string }
      await page.waitForTimeout(800)
      const alertEl = form.getByRole('alert').first()
      extra.request = { httpStatus: created.status(), code: p.code ?? null, title: p.title ?? null, detail: p.detail ?? null,
        alertTexts: (await form.getByRole('alert').allTextContents()).map((t) => t.replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 3),
        alertVisible: (await alertEl.count()) > 0 && await alertEl.isVisible(), focusAfter: await focused(page),
        notes: (await form.getByRole('note').allTextContents()).map((t) => t.trim()).filter(Boolean) }
      extra.detail = { opened: false, reason: 'theme draft request returned ' + created.status() }
    } else {
    const draft = await created.json() as { draftId: string; status: string; source: string; grade: string; weekStart: string; maxAttempts: number }
    extra.request = { httpStatus: created.status(), status: draft.status, source: draft.source, grade: draft.grade, weekStart: draft.weekStart, maxAttempts: draft.maxAttempts,
      notice: (await form.getByRole('status').allTextContents()).map((t) => t.trim()).filter(Boolean) }
    // learning 주기 작업(10초)이 ai를 불러 끝낼 때까지 상세 API로 상태 확인(화면이 보내는 요청의 Authorization 재사용, testing-ci 2절과 같은 방식)
    const auth = await new Promise<string>((resolve) => {
      page.on('request', (rq) => { const h = rq.headers().authorization; if (h && rq.url().includes('/api/v1/admin/')) resolve(h) })
      void page.locator('#admin-main').getByRole('button', { name: '목록 다시 확인' }).click()
    })
    let final: { status: string; attempts: number; failureCode: string | null; checkResults: { attempt: number; failures: { stage: string; reasons: string[] }[] }[] } | null = null
    const started = Date.now()
    await expect(async () => {
      const r = await page.request.get(`${BASE}/api/v1/admin/theme-drafts/${draft.draftId}`, { headers: { authorization: auth } })
      final = await r.json()
      expect(final!.status).not.toBe('GENERATING')
    }).toPass({ timeout: 20 * 60_000, intervals: [5_000] })
    const f = final!
    extra.generated = { seconds: Math.round((Date.now() - started) / 1000), status: f.status, attempts: f.attempts, failureCode: f.failureCode,
      failureStages: (f.checkResults ?? []).flatMap((c) => c.failures.map((x) => `${c.attempt}:${x.stage}`)), firstReason: f.checkResults?.[0]?.failures[0]?.reasons[0]?.slice(0, 160) ?? null }

    // ---- 상세 열기: 목록 "열기"(ux-audit adminDetails와 같은 방식) ----
    await go(page, '/admin/theme-drafts')
    await page.locator('#admin-main').getByRole('button', { name: '목록 다시 확인' }).click(); await settle(page)
    const open = page.locator('#admin-main').getByRole('button', { name: new RegExp(`${draft.weekStart}.*초안 열기`) }).first()
    await open.click(); await settle(page)
    await expect(page.locator('#admin-main').getByRole('heading', { name: /초안 상세/ }).first()).toBeVisible()
    const detailPath = new URL(page.url()).pathname + new URL(page.url()).search
    extra.detail = { opened: true, path: detailPath.replace(/[0-9a-f-]{36}/g, ':id'), headings: (await page.locator('#admin-main h2, #admin-main h3').allTextContents()).map((t) => t.trim()).slice(0, 12),
      buttons: (await page.locator('#admin-main button').allTextContents()).map((t) => t.trim()).filter(Boolean).slice(0, 20) }
    await a11y(page, 'admin', '테마 초안 상세', 1440)
    await contrastValues(page, '테마 초안 상세', 1440)
    for (const w of [1440, 768, 390]) await measureOverflow(page, 'admin', '테마 초안 상세', w)
    detailPathForTouch = detailPath
    extra.detailPath = detailPath.replace(/[0-9a-f-]{36}/g, ':id')
    }

    // ---- 2) 아이템 코드 중복 409(1440) ----
    await page.setViewportSize({ width: 1440, height: 900 })
    extra.adminDuplicate = [await duplicateItem(page, 1440)]

    // ---- 390 터치: 상세 접근성(초안이 있을 때) + 409 ----
    const touch: BrowserContextOptions = { viewport: { width: 390, height: 844 }, hasTouch: true }
    const at = await googleLogin(browser, admin, '/admin/login', '**/admin/home**', touch); contexts.push(at.context)
    if (detailPathForTouch) {
      await go(at.page, detailPathForTouch)
      await expect(at.page.locator('#admin-main').getByRole('heading', { name: /초안 상세/ }).first()).toBeVisible()
      await a11y(at.page, 'admin', '테마 초안 상세', 390)
      await contrastValues(at.page, '테마 초안 상세', 390)
    }
    ;(extra.adminDuplicate as unknown[]).push(await duplicateItem(at.page, 390))
  } finally {
    const s = (v: unknown) => JSON.stringify(v, null, 1)
    writeFileSync(join(OUT, 'extra.json'), s({ extra, overflow, axe, keyboard, states, contrast }) + '\n', 'utf8')
    for (const c of contexts) await c.close().catch(() => {})
  }
})
