import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { confirmPayment, orderPremium, returnToParent } from './support/payment.ts'

// 토스 결제 위젯(JS SDK)은 대역이 없어, 위젯의 성공 리다이렉트(/payment/success)를 직접 연다.
// 승인 요청은 core → toss-stub 실제 경로를 탄다.
test('유료 이용권 주문 → 결제 승인(toss-stub) → 이용권 적용', async ({ context, page }) => {
  await useGoogleIdentity(context, newParent('payment'))
  await onboardParent(page, `결제${Date.now().toString(36)}`)
  const ordered = await orderPremium(page)
  const { checkout, order } = ordered
  expect(order.amount).toBe(14900)
  expect(await page.evaluate(() => sessionStorage.getItem('sagomungchi:checkout:v1'))).toBeNull()
  expect(await checkout.evaluate(() => window.opener)).toBeNull()
  await confirmPayment(ordered)
  await expect(checkout.getByText('주문번호 ' + order.orderId)).not.toBeVisible()
  await checkout.getByText('거래 자세히 보기', { exact: true }).click()
  await expect(checkout.getByText('주문번호 ' + order.orderId)).toBeVisible()
  await returnToParent(page, checkout)
})
