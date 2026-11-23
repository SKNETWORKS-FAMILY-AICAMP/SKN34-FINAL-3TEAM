/**
 * #885 보조 확인(ux-audit.spec.ts 뒤 1회). 실행 방법·환경은 ux-audit.spec.ts와 같다. 결과: OUT_DIR/supplement.json(화면 글 없음)
 * 1) 대비 위반의 글자색·배경색·대비·글자 크기(axe color-contrast 노드 data만, html·failureSummary 없음)
 * 2) 390 터치에서 날짜 입력(게시 관리 "편성 시작 주")에 Tab으로 갔을 때 초점 표시(자동 검사에서 표시 변화 없음으로 나온 것 눈 확인용)
 * 3) 관리자 작업 목록을 늦게 받을 때 진행 안내(ux-audit에서 role=status 글 0건)
 */
import { expect, test, type Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { admin, useGoogleIdentity as signInWithGoogle } from '../../../../frontend/web/tests/e2e/support/google.ts'

const AXE = process.env.AXE_PATH!
const OUT = process.env.OUT_DIR ?? '.'
const SHOT = process.env.SHOT_DIR // 캡처는 저장소 밖(학생 글 없음 확인 전이라 넣지 않음)
const BASE = 'http://127.0.0.1:5272'

async function go(page: Page, path: string) {
  await page.evaluate((p) => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')) }, path)
  await page.waitForTimeout(1500)
}
async function contrast(page: Page) {
  if (!(await page.evaluate(() => 'axe' in window))) await page.addScriptTag({ path: AXE })
  return page.evaluate(async () => {
    // @ts-expect-error axe는 주입된 전역
    const r = await window.axe.run(document, { runOnly: { type: 'rule', values: ['color-contrast'] }, resultTypes: ['violations'] })
    const seen = new Map<string, { fg: string; bg: string; ratio: number; fontSize: string; fontWeight: string; expected: string; count: number }>()
    for (const v of r.violations) for (const n of v.nodes) {
      const d = (n.any[0]?.data ?? {}) as { fgColor: string; bgColor: string; contrastRatio: number; fontSize: string; fontWeight: string; expectedContrastRatio: string }
      const key = `${d.fgColor}|${d.bgColor}|${d.fontSize}|${d.fontWeight}`
      const s = seen.get(key)
      if (s) s.count++
      else seen.set(key, { fg: d.fgColor, bg: d.bgColor, ratio: d.contrastRatio, fontSize: d.fontSize, fontWeight: d.fontWeight, expected: d.expectedContrastRatio, count: 1 })
    }
    return [...seen.values()].sort((a, b) => b.count - a.count)
  })
}

test('#885 보조: 대비 값·날짜 입력 초점·관리자 진행 안내', async ({ browser }) => {
  test.setTimeout(600_000)
  const out: Record<string, unknown> = { run: new Date().toISOString() }
  const pub = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } })
  const p = await pub.newPage()
  await p.goto('/login'); await p.waitForTimeout(1500)
  out.parentLogin = await contrast(p)
  await p.goto('/admin/login'); await p.waitForTimeout(1500)
  out.adminLogin = await contrast(p)
  await pub.close()

  const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } })
  await signInWithGoogle(ctx, admin)
  const a = await ctx.newPage()
  await a.goto('/admin/login')
  await a.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await a.waitForURL('**/admin/home**'); await a.waitForTimeout(1500)
  out.adminContrast = {}
  for (const [name, path] of [['운영 현황', '/admin/home'], ['감사 이력', '/admin/audit'], ['작업 재처리', '/admin/jobs'], ['미션 관리', '/admin/missions']]) {
    await go(a, path)
    ;(out.adminContrast as Record<string, unknown>)[name] = await contrast(a)
  }
  // 작업 목록을 늦게 줄 때 보이는 것
  let release: () => void = () => {}
  const gate = new Promise<void>((r) => { release = r })
  await a.route('**/api/v1/admin/jobs**', async (route) => { await gate; await route.continue().catch(() => {}) })
  await go(a, '/admin/home'); await go(a, '/admin/jobs')
  out.adminJobsLoading = await a.evaluate(() => ({
    status: [...document.querySelectorAll('[role=status]')].map((e) => (e.textContent ?? '').trim()).filter(Boolean).slice(0, 3),
    busy: document.querySelectorAll('[aria-busy="true"]').length,
    loadingText: /불러오|불러오는/.test(document.querySelector('#admin-main')?.textContent ?? ''),
    emptyText: [...document.querySelectorAll('#admin-main .ad-empty')].map((e) => (e.textContent ?? '').trim().slice(0, 40)),
  }))
  release(); await a.unroute('**/api/v1/admin/jobs**')
  await ctx.close()

  // 390 터치: 날짜 입력 초점
  const t = await browser.newContext({ baseURL: BASE, viewport: { width: 390, height: 844 }, hasTouch: true })
  await signInWithGoogle(t, admin)
  const m = await t.newPage()
  await m.goto('/admin/login')
  await m.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await m.waitForURL('**/admin/home**'); await m.waitForTimeout(1500)
  await go(m, '/admin/themes')
  const input = m.getByLabel('편성 시작 주')
  await input.scrollIntoViewIfNeeded()
  // 앞 요소에 초점을 두고 Tab으로 들어감
  await input.evaluate((e) => { const prev = document.createElement('button'); prev.textContent = 'x'; e.parentElement!.insertBefore(prev, e); prev.focus(); prev.addEventListener('blur', () => prev.remove()) })
  await m.keyboard.press('Tab')
  await expect(input).toBeFocused()
  out.dateFocus390 = await input.evaluate((e) => {
    const s = getComputedStyle(e)
    return { focusVisible: e.matches(':focus-visible'), outline: `${s.outlineStyle} ${s.outlineWidth} ${s.outlineColor}`, boxShadow: s.boxShadow, border: s.borderColor }
  })
  if (SHOT) await m.locator('#admin-main').screenshot({ path: join(SHOT, '885-date-focus-390.png') })
  await t.close()
  writeFileSync(join(OUT, 'supplement.json'), JSON.stringify(out, null, 1) + '\n', 'utf8')
})
