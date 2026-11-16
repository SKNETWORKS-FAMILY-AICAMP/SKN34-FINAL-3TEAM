import { expect, type Page } from '@playwright/test'

/**
 * 이용권·결제에서 E2E 프리미엄 주문 → 결제수단 탭 → 성공 콜백(core → toss-stub 승인) → 원래 탭 이용권 적용까지.
 * 토스 결제 위젯(JS SDK)은 대역이 없어 위젯의 성공 리다이렉트(/payment/success)를 직접 연다.
 * 돌려주는 결제 탭은 닫히기 전 상태라 호출한 쪽이 결제 화면을 더 확인하고 닫는다.
 */
export async function orderPremium(page: Page) {
  await page.getByRole('link', { name: '이용권·결제' }).click()
  await expect(page.getByRole('heading', { name: '이용권·결제' })).toBeVisible()
  await page.getByRole('radio', { name: /E2E 프리미엄/ }).check()
  const popup = page.waitForEvent('popup')
  await page.getByRole('button', { name: '결제수단 선택' }).click()
  const checkout = await popup
  await expect(checkout.getByRole('heading', { name: '결제수단 선택', exact: true })).toBeVisible()
  // #548: only the checkout tab owns the order and its callback sessionStorage.
  const pending = await checkout.waitForFunction(() => sessionStorage.getItem('sagomungchi:checkout:v1'), undefined, { timeout: 30_000 })
  const order = JSON.parse((await pending.jsonValue()) as string) as { orderId: string; amount: number }
  return { checkout, order }
}

export async function confirmPayment({ checkout, order }: Awaited<ReturnType<typeof orderPremium>>) {
  await checkout.goto('/payment/success?' + new URLSearchParams({
    paymentKey: `e2e-pk-${order.orderId}`, orderId: order.orderId, amount: String(order.amount),
  }))
  await expect(checkout.getByRole('heading', { name: '결제가 완료되었습니다' })).toBeVisible()
}

export async function returnToParent(page: Page, checkout: Page) {
  await checkout.close()
  await page.bringToFront()
  // Headless CI has no OS tab focus; invoke the same focus listener explicitly.
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: /E2E 프리미엄.*이용 중/ })).toBeVisible()
}

/** 프리미엄 이용권 적용(리포트 서술·설명 FN-RPT-09) */
export async function subscribePremium(page: Page) {
  const ordered = await orderPremium(page)
  await confirmPayment(ordered)
  await returnToParent(page, ordered.checkout)
}
