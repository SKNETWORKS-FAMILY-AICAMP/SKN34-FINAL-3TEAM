import { expect, test } from '@playwright/test'

const order = {
  orderId: 'checkout-state-test',
  productId: '74000000-0000-4000-8000-000000000001',
  childId: 'demo-seoyun',
  amount: 14900,
  orderName: '프리미엄',
  confirmKey: '00000000-0000-4000-8000-000000000815',
}

test('닫힌 결제 탭을 같은 주문 키와 자녀로 다시 연다', async ({page}) => {
  await page.goto('/login')
  await page.getByRole('button', {name:'시연 계정으로 로그인',exact:true}).click()
  await expect(page).toHaveURL(/parent\/journal/)
  await page.goto('/parent/billing?childId=demo-doyun')
  await page.getByRole('radio', {name:/프리미엄/}).check()
  const opened = page.waitForEvent('popup')
  await page.getByRole('button', {name:'결제수단 선택',exact:true}).click()
  const tab = await opened
  await tab.waitForURL('**/parent/billing?**')
  const url = tab.url()
  expect(new URL(url).searchParams.get('orderKey')).toBeTruthy()
  expect(new URL(url).searchParams.get('childId')).toBe('demo-doyun')
  await tab.close()
  const reopened = page.waitForEvent('popup')
  await page.getByRole('button',{name:'결제 탭 다시 열기'}).click()
  await expect(await reopened).toHaveURL(url)
})

for (const initial of ['PENDING', 'CONFIRMING', 'FAILED_TO_LOAD'] as const) {
  test(`결제 화면은 주문 상태를 한 번 조회하고 같은 결과로 결제를 제어한다 (${initial})`, async ({ page }) => {
    await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
    await page.goto('/login')
    await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
    await expect(page).toHaveURL(/\/parent\/journal/)
    await page.addInitScript(({ order, initial }) => {
      sessionStorage.setItem('sagomungchi:checkout:v1', JSON.stringify({ ...order, createdAt: Date.now() }))
      let status: string = initial
      let count = 0
      const originalFetch = window.fetch.bind(window)
      window.addEventListener('checkout-test-state', event => {
        status = (event as CustomEvent<string>).detail
        window.dispatchEvent(new Event('sagomungchi:payment-fixture-updated'))
      })
      window.fetch = (input, init) => {
        const url = new URL(input instanceof Request ? input.url : String(input), location.href)
        if (url.pathname !== `/api/v1/payments/${order.orderId}`) return originalFetch(input, init)
        document.documentElement.dataset.checkoutQueries = String(++count)
        return Promise.resolve(status === 'FAILED_TO_LOAD'
          ? Response.json({ code: 'QUERY_FAILED', status: 503, title: '주문 상태 조회 실패' }, { status: 503 })
          : Response.json({ ...order, status, paymentId: null, entitlementStatus: null, approvedAt: null, failureCode: null }))
      }
    }, { order, initial })
    await page.goto('/parent/billing?' + new URLSearchParams({ childId: order.childId, productId: order.productId, checkout: '1' }))
    const queries = page.locator('html')
    const pay = page.getByRole('button', { name: '14,900원 결제하기', exact: true })
    const confirming = page.getByText('결제 결과를 확인하고 있습니다. 다시 결제하지 마세요.', { exact: true })
    if (initial === 'PENDING') {
      await expect(pay).toBeEnabled()
    } else if (initial === 'CONFIRMING') {
      await expect(confirming).toBeVisible()
      await expect(pay).toHaveCount(0)
    } else {
      await expect(page.getByRole('alert').filter({ hasText: '주문 상태 조회 실패' })).toHaveCount(1)
      await expect(pay).toBeDisabled()
    }
    await expect(queries).toHaveAttribute('data-checkout-queries', '1')
    if (initial === 'PENDING') {
      await page.evaluate(() => window.dispatchEvent(new CustomEvent('checkout-test-state', { detail: 'CONFIRMING' })))
      await expect(confirming).toBeVisible()
      await expect(pay).toHaveCount(0)
      await expect(queries).toHaveAttribute('data-checkout-queries', '2')
    }
  })
}
