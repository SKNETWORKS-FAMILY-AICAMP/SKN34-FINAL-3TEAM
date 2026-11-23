import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { appendFileSync } from 'node:fs'
import { admin, useGoogleIdentity } from './support/google.ts'
const OUT = process.env.FOCUS_OUT! // 결과 jsonl 경로(경우마다 한 줄)
const focus = (page: Page) => page.evaluate(() => { const a = document.activeElement as HTMLElement | null; return a ? `${a.tagName}${a.textContent ? ':' + a.textContent.trim().slice(0, 20) : ''}${a.getAttribute('aria-disabled') ? '[aria-disabled]' : ''}${(a as HTMLButtonElement).disabled ? '[disabled]' : ''}` : 'null' })
async function slow(page: Page) {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const request = new Request(input, init)
      if (request.method === 'POST' && /\/api\/v1\/admin\/(look-items|theme-drafts)$/.test(new URL(request.url).pathname)) await new Promise(r => setTimeout(r, 1000))
      return original(input, init)
    }
  })
}
async function enter(page: Page, width: number, label: string) {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
  await page.goto('/admin/login')
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL('**/admin/home**')
  await page.locator('h1').first().waitFor()
  const menu = page.getByRole('button', { name: '메뉴', exact: true })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('navigation', { name: '관리자 메뉴' }).getByRole('link', { name: label, exact: true }).click()
  await page.locator('h1').first().waitFor()
}
for (const width of [1440, 390]) {
  test(`look item 409 ${width}`, async ({ context, page }) => {
    await useGoogleIdentity(context, admin); await slow(page)
    await enter(page, width, '꾸미기 아이템')
    await page.getByRole('button', { name: '새 아이템', exact: true }).click()
    await page.getByLabel('아이템 코드', { exact: true }).fill('E2E_HAT')
    await page.getByLabel('아이템 칸', { exact: true }).selectOption('HAT')
    await page.getByLabel('아이템 이름', { exact: true }).fill('중복 확인')
    await page.getByLabel('필요 포인트', { exact: true }).fill('10')
    await page.getByLabel('그림 키', { exact: true }).fill('looks/hat-acorn.svg')
    const save = page.getByRole('button', { name: '저장', exact: true })
    await save.focus(); await page.keyboard.press('Enter')
    await page.waitForTimeout(400); const during = await focus(page)
    const alert = page.getByRole('alert').filter({ hasText: '이미 있는 코드입니다.' })
    await expect(alert).toBeVisible()
    const after = await focus(page), inView = await alert.evaluate(el => { const r = el.getBoundingClientRect(); return r.top >= -1 && r.bottom <= innerHeight + 1 })
    appendFileSync(OUT, JSON.stringify({ case: '꾸미기 아이템 저장 409', width, during, after, alertInViewport: inView }) + '\n')
  })
  test(`theme request error ${width}`, async ({ context, page }) => {
    await useGoogleIdentity(context, admin); await slow(page)
    await enter(page, width, '주간 테마 검수')
    await page.getByText('새 테마 초안 요청', { exact: true }).click()
    const button = page.locator('.ad-request-panel button.cj-primary')
    // 같은 학년·주 요청을 두 번 보내 두 번째를 오류로 만든다(첫 번째는 마우스).
    await button.click(); await expect(button).toHaveText('테마 초안 생성 요청', { timeout: 15000 })
    await button.focus(); await page.keyboard.press('Enter')
    await page.waitForTimeout(400); const during = await focus(page)
    await expect(button).toHaveText('테마 초안 생성 요청', { timeout: 15000 })
    await page.waitForTimeout(300)
    const alert = page.locator('.ad-request-panel [role="alert"]').first()
    const hasAlert = await alert.count() > 0
    const after = await focus(page), text = hasAlert ? (await alert.innerText()).split('\n')[0] : (await page.locator('.ad-request-panel [role="status"]').allInnerTexts()).join(' / ')
    const inView = hasAlert ? await alert.evaluate(el => { const r = el.getBoundingClientRect(); return r.top >= -1 && r.bottom <= innerHeight + 1 }) : null
    appendFileSync(OUT, JSON.stringify({ case: '테마 초안 생성 요청(두 번째)', width, during, after, message: text, alertInViewport: inView }) + '\n')
  })
}
