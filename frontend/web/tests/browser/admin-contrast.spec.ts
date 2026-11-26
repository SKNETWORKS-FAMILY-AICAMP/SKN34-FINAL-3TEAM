import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #914: 관리자 보조 글·표 글·로그인 글 대비(WCAG 1.4.3)와 390px 가로 스크롤 표 키보드 접근(WCAG 2.1.1) 회귀 시험
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function login(page: Page) {
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill('admin@example.test')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page.getByRole('heading', { name: '운영 요약', exact: true })).toBeVisible()
}

async function navigate(page: Page, label: string) {
  const menu = page.getByRole('button', { name: '메뉴', exact: true })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('navigation', { name: '관리자 메뉴' }).getByRole('link', { name: label, exact: true }).click()
  await expect(page.locator('.ad-location strong')).toHaveText(label)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.locator('.ad-table-wrap, .ad-empty, .ws-card, .ad-inbox-row').filter({ visible: true }).first()).toBeVisible()
}

/** 글자가 있는 보이는 요소마다 글자색과 가장 가까운 불투명 배경의 대비를 잰다. 꺼진 컨트롤은 WCAG 예외라 뺀다. */
async function lowContrast(page: Page) {
  return page.evaluate(() => {
    const rgba = (color: string) => color.match(/[\d.]+/g)!.map(Number)
    const luminance = ([r, g, b]: number[]) => [r, g, b].map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 })
      .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0)
    const failures: string[] = []
    for (const el of document.querySelectorAll<HTMLElement>('body *')) {
      const text = [...el.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent?.trim()).join('')
      if (!text || el.closest(':disabled,[aria-hidden="true"],.sr-only,svg')) continue
      const style = getComputedStyle(el)
      const box = el.getBoundingClientRect()
      if (style.visibility !== 'visible' || Number(style.opacity) === 0 || !box.width || !box.height) continue
      const fg = rgba(style.color)
      if (fg[3] !== undefined && fg[3] < 1) continue
      let bg: Element | null = el, bgColor: number[] | undefined
      while (bg) {
        const s = getComputedStyle(bg)
        if (s.backgroundImage !== 'none') break
        const c = rgba(s.backgroundColor)
        if (c[3] === undefined || c[3] === 1) { bgColor = c; break }
        bg = bg.parentElement
      }
      if (!bgColor) continue
      const [hi, lo] = [luminance(fg), luminance(bgColor)].sort((a, b) => b - a)
      const ratio = (hi + 0.05) / (lo + 0.05)
      const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700)
      if (ratio < (large ? 3 : 4.5)) failures.push(`${el.tagName.toLowerCase()}.${el.className} "${text.slice(0, 20)}" ${style.color} / ${getComputedStyle(bg!).backgroundColor} ${ratio.toFixed(2)}`)
    }
    return failures
  })
}

const screens = ['감사 이력', '주간 테마 검수', '미션 관리', '미션 초안', '작업 재처리', '모델·프롬프트', '표현 검토', 'AI 사용량', '결제·환불', '문의·공지', '꾸미기 아이템']

test('관리자 로그인과 주요 관리자 화면의 글자 대비가 4.5:1 이상이다 @responsive', async ({ page }) => {
  test.setTimeout(90_000)
  await page.goto('/admin/login')
  await expect(page.getByRole('button', { name: '로그인', exact: true })).toBeVisible()
  expect(await lowContrast(page)).toEqual([])
  await login(page)
  expect(await lowContrast(page)).toEqual([])
  for (const label of screens) {
    await navigate(page, label)
    expect(await lowContrast(page), label).toEqual([])
  }
})

test('관리자 공통 초점 외곽선은 흰 배경과 3:1 이상이다', async ({ page }) => {
  await login(page)
  await navigate(page, '감사 이력')
  await page.keyboard.press('Tab')
  const ratio = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement
    const rgb = getComputedStyle(el).outlineColor.match(/[\d.]+/g)!.slice(0, 3).map(Number)
    const l = rgb.map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }).reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0)
    return 1.05 / (l + 0.05)
  })
  expect(ratio).toBeGreaterThanOrEqual(3)
})

test('390px에서 넘치는 표는 이름 있는 영역으로 키보드 초점을 받아 가로로 밀린다 @responsive', async ({ page }) => {
  await login(page)
  await navigate(page, 'AI 사용량')
  const region = page.getByRole('region', { name: 'AI 사용량 표', exact: true })
  await expect(region).toBeVisible()
  const overflows = await region.evaluate(el => el.scrollWidth > el.clientWidth + 1)
  // 시험 자료로 390·1024px에서는 넘치고 1440px에서는 넘치지 않는다(#1051 실패율·p50·p95 열 추가로 8열).
  expect(overflows).toBe(page.viewportSize()!.width < 1440)
  if (!overflows) {
    // 넓은 화면에서 넘치지 않으면 Tab 순서에 끼지 않는다.
    await expect(region).not.toHaveAttribute('tabindex')
    return
  }
  await expect(region).toHaveAttribute('tabindex', '0')
  await page.getByRole('heading', { level: 1 }).click()
  for (let i = 0; i < 40 && !(await region.evaluate(el => el === document.activeElement)); i++) await page.keyboard.press('Tab')
  await expect(region).toBeFocused()
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('End')
  await expect.poll(() => region.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
})
