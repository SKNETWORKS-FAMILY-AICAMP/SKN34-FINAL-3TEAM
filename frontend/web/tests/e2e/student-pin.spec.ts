import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'

test('Google 로그인 보호자는 추가 재인증 없이 선택한 자녀 PIN을 저장한다', async ({ context, page }) => {
  const nickname = `핀학생${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('pin'))
  await onboardParent(page, nickname)
  const reauth: string[] = []
  page.on('request', request => { if (new URL(request.url()).pathname.includes('/me/reauth')) reauth.push(request.url()) })
  await page.getByRole('link', { name: '기기·PIN', exact: true }).click()
  const form = page.getByRole('form', { name: `${nickname} PIN`, exact: true })
  await form.getByLabel(`${nickname} 새 PIN`, { exact: true }).fill('4831')
  await form.getByLabel(`${nickname} 새 PIN 확인`, { exact: true }).fill('4831')
  await expect(form.getByRole('button', { name: /Google|본인 확인/ })).toHaveCount(0)
  const saved = page.waitForResponse(response => response.request().method() === 'PUT' && new URL(response.url()).pathname.endsWith('/pin'))
  await form.getByRole('button', { name: 'PIN 정하기', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(204)
  expect(response.request().headers()['x-reauth-token']).toBeUndefined()
  await expect(form.getByRole('status')).toContainText(`${nickname}의 PIN을 저장했습니다.`)
  await expect(form.locator('[data-pin-state]')).toHaveAttribute('data-pin-state', 'set')
  expect(reauth).toEqual([])
})
