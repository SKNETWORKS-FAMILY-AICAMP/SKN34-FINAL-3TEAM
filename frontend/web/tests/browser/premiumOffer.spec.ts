import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/parent\/journal/)
}

test('premium stays visible and change previews never create purchases @responsive', async ({ page }, info) => {
  const mutations: string[] = []
  page.on('request', request => {
    if (request.method() !== 'GET' && /\/api\/v1\/(orders|subscriptions)(\/|$)/.test(new URL(request.url()).pathname)) mutations.push(request.url())
  })
  await login(page)
  await page.goto('/parent/billing?childId=demo-doyun')
  const offer = page.getByRole('region', { name: '프리미엄 이용권', exact: true })
  await expect(offer).toHaveCount(1)
  await expect(offer.locator('.premium-price strong')).toHaveText('14,900원')
  await expect(offer.getByRole('button', { name: '결제수단 선택', exact: true })).toBeEnabled()
  await expect(page.locator('.parent-free-plan')).toHaveCount(0)
  await expect(page.locator('#plan-compare')).toBeVisible()
  await page.screenshot({ path: info.outputPath('premium-offer.png') })
  await offer.locator('.premium-benefits').scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('premium-benefits.png') })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.goto('/parent/billing?childId=demo-seoyun')
  await expect(offer).toHaveCount(1)
  const change = page.getByRole('button', { name: '이용권 변경', exact: true })
  await expect(change).toBeVisible()
  await page.screenshot({ path: info.outputPath('premium-management.png') })
  await change.click()
  const preview = page.getByRole('region', { name: '이용권 변경', exact: true })
  await expect(preview.getByRole('heading', { name: '이용권 변경', exact: true })).toBeFocused()
  await expect.poll(() => page.evaluate(() => {
    const topbar = document.querySelector('.ws-parent-topbar')?.getBoundingClientRect()
    const heading = document.querySelector('.premium-preview .premium-catalog-heading')?.getBoundingClientRect()
    return !!topbar && !!heading && heading.top >= topbar.bottom && heading.bottom <= innerHeight
  })).toBe(true)
  await expect(offer.getByText('이용 중', { exact: true })).toBeVisible()
  await expect(offer.getByRole('link', { name: '현재 구독 관리', exact: true })).toBeVisible()
  await expect(offer.getByRole('button', { name: '결제수단 선택', exact: true })).toHaveCount(0)
  await expect(preview).toContainText('가격 미확정 시안')
  for (const price of [9900, 12900, 14900, 19900]) {
    await expect(preview.getByRole('button', { name: `${price.toLocaleString('ko-KR')}원 이용권 변경 · 시안`, exact: true })).toBeDisabled()
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.screenshot({ path: info.outputPath('premium-subscribed.png') })
  await preview.screenshot({ path: info.outputPath('premium-candidates.png'), style: '.ws-parent-topbar, .ws-bottom-nav { visibility:hidden !important; }' })
  await page.getByRole('button', { name: '목록 닫기', exact: true }).click()
  await expect(preview).toHaveCount(0)
  await expect(offer).toHaveCount(1)
  await expect(change).toBeFocused()
  expect(mutations).toEqual([])
  await offer.getByRole('link', { name: '현재 구독 관리', exact: true }).click()
  await expect(page.getByRole('region', { name: '현재 구독', exact: true })).toBeVisible()
  await page.goto('/parent/billing?childId=demo-doyun#plan-compare')
  await expect(page.locator('#plan-compare').getByRole('table')).toBeVisible()
  await expect(page.getByRole('heading', { name: '무료·프리미엄 비교', exact: true })).toBeVisible()
})

test('premium price follows the product API and never falls back to a candidate @responsive', async ({ page }, info) => {
  await page.addInitScript(() => {
    let price = 9900
    window.addEventListener('premium-test-price', event => { price = (event as CustomEvent<number>).detail })
    const original = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), location.href)
      const response = await original(input, init)
      if (url.pathname !== '/api/v1/products') return response
      if (price < 0) return Response.json({ title: '상품 조회 실패', status: 503, code: 'PRODUCTS_UNAVAILABLE' }, { status: 503 })
      const data = await response.json()
      return Response.json({ ...data, items: data.items.map((p: { code: string; price: number }) => p.code === 'PREMIUM' ? { ...p, price } : p) })
    }
  })
  await login(page)
  await page.goto('/parent/billing?childId=demo-doyun')
  for (const price of [9900, 12900, 14900, 19900]) {
    await page.evaluate(price => { window.dispatchEvent(new CustomEvent('premium-test-price', { detail: price })); window.dispatchEvent(new Event('focus')) }, price)
    await expect(page.locator('.premium-price strong')).toHaveText(`${price.toLocaleString('ko-KR')}원`)
  }
  await page.evaluate(() => { window.dispatchEvent(new CustomEvent('premium-test-price', { detail: -1 })); window.dispatchEvent(new Event('focus')) })
  await expect(page.getByRole('alert').filter({ hasText: '상품 조회 실패' })).toBeVisible()
  // A previously cached product must not offer a new purchase after a failed product refresh.
  await expect(page.getByRole('button', { name: '결제수단 선택', exact: true })).toBeDisabled()
  await page.screenshot({ path: info.outputPath('premium-error.png') })
})

test('catalog includes every active monthly product and checkout keeps the chosen product @responsive', async ({ page, context }, info) => {
  await context.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), location.href)
      if (url.pathname === '/api/v1/orders') {
        const body = JSON.parse(String(init?.body ?? '{}'))
        if (body.productId === 'catalog-extra') return Response.json({ orderId: 'catalog-checkout', childId: body.childId, productId: body.productId, amount: 18000, orderName: '추가 이용권 · 검사 전용' }, { status: 201 })
      }
      if (url.pathname === '/api/v1/payments/catalog-checkout') return Response.json({ orderId: 'catalog-checkout', childId: 'demo-doyun', amount: 18000, status: 'PENDING', paymentId: null, entitlementStatus: null, approvedAt: null, failureCode: null })
      const response = await original(input, init)
      if (url.pathname !== '/api/v1/products') return response
      const data = await response.json()
      const base = data.items.find((p: { code: string }) => p.code === 'PREMIUM')
      return Response.json({ ...data, items: [...data.items,
        { ...base, id: 'catalog-extra', code: 'CATALOG_EXTRA', name: '추가 이용권 · 검사 전용', price: 18000 },
        { ...base, id: 'catalog-retired', code: 'CATALOG_RETIRED', name: '판매 종료 상품', active: false },
      ] })
    }
  })
  await login(page)
  await page.goto('/parent/billing?childId=demo-doyun')
  const catalog = page.getByRole('region', { name: '이용 가능한 이용권', exact: true })
  await expect(catalog.locator('.premium-offer')).toHaveCount(2)
  await expect(catalog.getByRole('heading', { name: '판매 종료 상품', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.screenshot({ path: info.outputPath('premium-catalog-multiple.png') })
  const extra = catalog.getByRole('region', { name: '추가 이용권 · 검사 전용 이용권', exact: true })
  const opened = page.waitForEvent('popup')
  await extra.getByRole('button', { name: '결제수단 선택', exact: true }).click()
  const checkout = await opened
  await checkout.waitForURL('**/parent/billing?**')
  expect(new URL(checkout.url()).searchParams.get('productId')).toBe('catalog-extra')
  expect(new URL(checkout.url()).searchParams.get('childId')).toBe('demo-doyun')
  await expect(checkout.getByRole('button', { name: '18,000원 결제하기', exact: true })).toBeEnabled()
  await checkout.close()
})
