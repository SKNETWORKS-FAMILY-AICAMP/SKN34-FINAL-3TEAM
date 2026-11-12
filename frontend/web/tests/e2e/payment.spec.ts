import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'

// 토스 결제 위젯(JS SDK)은 대역이 없어, 위젯의 성공 리다이렉트(/payment/success)를 직접 연다.
// 승인 요청은 core → toss-stub 실제 경로를 탄다.
test('유료 이용권 주문 → 결제 승인(toss-stub) → 이용권 적용', async ({ context, page }) => {
  await useGoogleIdentity(context, newParent('payment'))
  await onboardParent(page, `결제${Date.now().toString(36)}`)
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
  expect(order.amount).toBe(14900)
  expect(await page.evaluate(() => sessionStorage.getItem('sagomungchi:checkout:v1'))).toBeNull()
  expect(await checkout.evaluate(() => window.opener)).toBeNull()
  await checkout.goto('/payment/success?' + new URLSearchParams({
    paymentKey: `e2e-pk-${order.orderId}`, orderId: order.orderId, amount: String(order.amount),
  }))
  await expect(checkout.getByRole('heading', { name: '결제가 완료되었습니다' })).toBeVisible()
  await expect(checkout.getByText('주문번호 ' + order.orderId)).not.toBeVisible()
  await checkout.getByText('거래 자세히 보기', { exact: true }).click()
  await expect(checkout.getByText('주문번호 ' + order.orderId)).toBeVisible()
  await checkout.close()
  await page.bringToFront()
  // Headless CI has no OS tab focus; invoke the same focus listener explicitly.
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: /E2E 프리미엄.*이용 중/ })).toBeVisible()
})
