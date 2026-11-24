import { test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { appendFileSync } from 'node:fs'
import { admin, useGoogleIdentity } from './support/google.ts'
const AXE = process.env.AXE_PATH! // axe-core 4.10.2 axe.min.js 경로
const OUT = process.env.AXE_OUT! // 결과 jsonl 경로(화면마다 한 줄)
async function audit(page: Page, name: string) {
  await page.waitForTimeout(1200)
  await page.addScriptTag({ path: AXE })
  const r = await page.evaluate(async () => {
    // @ts-expect-error axe global
    const res = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] } })
    return res.violations.filter((v: { impact: string }) => v.impact === 'serious' || v.impact === 'critical').map((v: { id: string; nodes: { target: string[]; any: { data?: { fgColor?: string; bgColor?: string; contrastRatio?: number } }[] }[] }) => ({ id: v.id, nodes: v.nodes.map(n => ({ t: n.target.join(' '), d: n.any[0]?.data && { fg: n.any[0].data.fgColor, bg: n.any[0].data.bgColor, r: n.any[0].data.contrastRatio } })) }))
  })
  appendFileSync(OUT, JSON.stringify({ name, w: page.viewportSize()!.width, url: page.url().replace(/^https?:\/\/[^/]+/, ''), n: r.reduce((s: number, v: { nodes: unknown[] }) => s + v.nodes.length, 0), r }) + '\n')
}
for (const width of [1440, 390]) test(`real axe admin ${width}`, async ({ context, page }) => {
  test.setTimeout(600_000)
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
  await useGoogleIdentity(context, admin)
  await page.goto('/admin/login')
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).waitFor()
  await audit(page, '관리자 로그인')
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL('**/admin/home**')
  await page.locator('h1').first().waitFor()
  const menu = page.getByRole('button', { name: '메뉴', exact: true })
  if (await menu.isVisible()) await menu.click()
  const nav = page.getByRole('navigation', { name: '관리자 메뉴' })
  await nav.getByRole('link').first().waitFor({ state: 'attached' })
  const links = await nav.getByRole('link').evaluateAll(as => as.map(a => [a.textContent?.trim() ?? '', a.getAttribute('href') ?? '']))
  for (const [label, href] of links) {
    await page.goto(href)
    await page.locator('h1').first().waitFor()
    await audit(page, label)
    if (href.startsWith('/admin/jobs')) { const b = page.getByRole('button', { name: '작업 상세' }).first(); if (await b.count()) { await b.click(); await audit(page, '작업 상세') } }
    if (href.startsWith('/admin/missions')) { const b = page.getByRole('button', { name: /편집|수정/ }).first(); if (await b.count()) { await b.click(); await audit(page, '미션 편집') } }
    if (href.startsWith('/admin/theme-drafts')) { const b = page.getByRole('button', { name: /검수|열기|상세/ }).first(); if (await b.count()) { await b.click(); await audit(page, '테마 초안 상세') } }
  }
})
