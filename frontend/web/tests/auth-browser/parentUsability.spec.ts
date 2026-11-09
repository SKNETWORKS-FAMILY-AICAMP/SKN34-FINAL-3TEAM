import { test, expect } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

async function capture(page: Page, name: string) {
  const out = '.taste-skill/usability/remaining'
  await mkdir(out, { recursive: true })
  const css = await page.evaluate(async () => Promise.all([...document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')]
    .filter(link => new URL(link.href).origin === location.origin).map(async link => (await fetch(link.href)).text())))
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    await page.screenshot({ path: `${out}/${name}-${width}.png`, fullPage: true })
    const html = (await page.content()).replace(/<script\b[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*rel="stylesheet"[^>]*>/gi, '')
      .replace('<head>', '<head><base href="http://127.0.0.1:5278/">' + css.map(text => '<style>' + text + '</style>').join(''))
    await writeFile(`${out}/${name}-${width}.html`, html)
  }
}

// 운영 빌드의 화면 계약 검사. 결제 승인 실연동은 tests/e2e/payment.spec.ts에서 별도로 확인한다.
async function parentServer(context: BrowserContext, mode: 'normal' | 'consent' | 'error' | 'empty' | 'history' = 'normal') {
  const child = { id: '00000000-0000-4000-8000-000000000001', nickname: '별빛', grade: 3, birthYear: 2017 }
  const free = { id: 'free', code: 'FREE', name: '기본 이용권', price: 0, billingCycle: 'NONE', childLimit: 1, active: true, features: {}, limits: {} }
  const product = { ...free, id: 'premium', code: 'PREMIUM', name: '프리미엄 이용권', price: 14900, billingCycle: 'MONTHLY' }
  const calls: string[] = []
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    calls.push(request.method() + ' ' + path)
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    const nextAction = mode === 'consent' ? 'CONSENT_REQUIRED' : 'READY'
    if (path === '/auth/refresh') return json({ accessToken: 'synthetic-parent', expiresIn: 900, role: 'PARENT', nextAction, startPath: '/parent/onboarding' })
    if (path === '/me') return json({ userId: 'parent', role: 'PARENT', authMethod: 'GOOGLE', name: '합성 보호자', email: 'parent@example.test', permissions: [], nextAction, startPath: '/parent/onboarding' })
    if (path === '/children') return mode === 'consent' ? json({ code: 'CONSENT_REQUIRED' }, 403) : json({ items: [child] })
    if (path.endsWith('/entitlement')) return json({ childId: child.id, product: free, status: 'FREE', autoRenew: false, refundPending: false, conversationEnabled: false, narrativeEnabled: false })
    if (path === '/products') return mode === 'error' ? json({ status: 503, code: 'PRODUCTS_UNAVAILABLE', title: '이용권을 불러오지 못했습니다.', detail: '상품 조회 연결 실패', traceId: 'trace-synthetic' }, 503) : json({ items: mode === 'empty' ? [] : [free, product] })
    if (path === '/subscriptions') return json({ items: [] })
    if (path === '/payments') return json({ items: mode === 'history' ? [{ paymentId: 'payment-1', orderId: 'synthetic-order-123456', childId: child.id, amount: 14900, status: 'UNKNOWN_STATUS', approvedAt: '2026-11-09T00:00:00Z', subscription: null, refundRequests: [{ id: 'refund-1', status: 'UNKNOWN_REFUND', rejectReason: null }] }] : [] })
    if (path.endsWith('/deletion-impact')) return json({ childId: child.id, actions: [], retainedTransactionsYears: 5, deviceCleanupPending: false })
    if (path === '/notifications') return json({ items: [], page: 0, size: 20, hasNext: false })
    if (path === '/notifications/stream') return route.abort('failed')
    return json({ code: 'NOT_FOUND' }, 404)
  })
  return calls
}

test('예전 계정 주소는 자녀·기간 조건을 보존해 유일한 계정 관리 탭으로 연결한다', async ({ page, context }) => {
  await parentServer(context)
  await page.goto('/parent/account?childId=00000000-0000-4000-8000-000000000001&from=2026-11-01&to=2026-11-09')
  await expect(page.getByRole('tab', { name: '계정 관리', exact: true })).toHaveAttribute('aria-selected', 'true')
  expect(new URL(page.url()).pathname).toBe('/parent/settings')
  expect(new URL(page.url()).searchParams.get('from')).toBe('2026-11-01')
  await expect(page.getByRole('heading', { name: '회원 탈퇴', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '본인 정보', exact: true })).toHaveCount(0)
  await capture(page, 'account')
})

test('이용 동의 전에도 계정 관리와 탈퇴에 접근하고 금지된 자녀 조회는 요청하지 않는다', async ({ page, context }) => {
  const calls = await parentServer(context, 'consent')
  await page.goto('/parent/account')
  await expect(page.getByRole('heading', { name: '회원 탈퇴', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '자녀 등록', exact: true })).toHaveCount(0)
  expect(calls).not.toContain('GET /children')
})

test('오류 안내는 먼저 보이고 코드와 확인 번호는 자세히를 열 때만 보인다', async ({ page, context }) => {
  await parentServer(context, 'error')
  await page.goto('/parent/billing')
  const notice = page.getByRole('alert').filter({ hasText: '이용권을 불러오지 못했습니다.' })
  await expect(notice).toBeVisible()
  await expect(notice.getByText(/PRODUCTS_UNAVAILABLE/)).not.toBeVisible()
  await capture(page, 'error')
  await notice.getByText('문제 자세히 보기', { exact: true }).click()
  await expect(notice.getByText(/PRODUCTS_UNAVAILABLE/)).toBeVisible()
  await expect(notice.getByText(/trace-synthetic/)).toBeVisible()
})

test('판매 상품이 없으면 빈 주문 확인과 비활성 구매 버튼을 보여 주지 않는다', async ({ page, context }) => {
  const calls = await parentServer(context, 'empty')
  await page.goto('/parent/billing')
  await expect(page.getByText('현재 구매 가능한 이용권이 없습니다.', { exact: false })).toBeVisible()
  await expect(page.getByRole('heading', { name: '주문 확인', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '결제수단 선택', exact: true })).toHaveCount(0)
  expect(calls.some(call => call.startsWith('POST /orders'))).toBe(false)
})

test('결제 설정 장애는 문의 경로와 사용자 문구를 보여 주고 주문을 만들지 않는다', async ({ page, context }) => {
  const calls = await parentServer(context)
  await page.goto('/parent/billing')
  await expect(page.getByRole('note').filter({ hasText: '지금 결제를 이용할 수 없어요.' })).toBeVisible()
  await page.getByRole('radio', { name: /프리미엄 이용권/ }).check()
  await expect(page.getByRole('button', { name: '결제수단 선택', exact: true })).toBeDisabled()
  expect(calls.some(call => call.startsWith('POST /orders'))).toBe(false)
})

test('거래에는 자녀 별명을 쓰고 미지의 상태 코드와 주문번호를 기본 화면에 노출하지 않는다', async ({ page, context }) => {
  await parentServer(context, 'history')
  await page.goto('/parent/billing')
  await expect(page.getByText('대상 자녀 별빛', { exact: false })).toBeVisible()
  await expect(page.getByText(/UNKNOWN_STATUS|UNKNOWN_REFUND/)).toHaveCount(0)
  await expect(page.getByText('주문번호 synthetic-order-123456', { exact: true })).not.toBeVisible()
  await capture(page, 'payment-history')
  await page.getByText('거래 자세히 보기', { exact: true }).click()
  await expect(page.getByText('주문번호 synthetic-order-123456', { exact: true })).toBeVisible()
})
