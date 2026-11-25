import { expect, test, type Page } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent, parentGuide } from './support/onboarding.ts'

// 학부모 첫 사용 안내(#1037): 완료 기록은 core `/me/onboarding`(#1035)에 남는다.
const onboardingPut = (page: Page) =>
  page.waitForResponse(r => r.request().method() === 'PUT' && new URL(r.url()).pathname.endsWith('/me/onboarding'))

async function logout(page: Page) {
  await page.getByRole('button', { name: '로그아웃', exact: true }).first().click()
  await page.waitForURL('**/login**')
}
async function loginAgain(page: Page, nickname: string) {
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL('**/parent/journal**')
  await expect(page.getByRole('heading', { name: `${nickname}의 학습 현황` })).toBeVisible()
}

test('가입 뒤 안내가 뜨고, 건너뛰면 다시 로그인해도 뜨지 않는다', async ({ context, page }) => {
  const nickname = `안내건너${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('guide-skip'))
  await onboardParent(page, nickname, { keepGuide: true })
  const guide = parentGuide(page)
  await expect(guide.getByRole('heading', { name: '먼저 아이 기기를 등록해 주세요' })).toBeFocused()
  const saved = onboardingPut(page)
  await guide.getByRole('button', { name: '건너뛰기', exact: true }).click()
  const { completedAt } = await (await saved).json() as { completedAt: string | null }
  expect(typeof completedAt).toBe('string')
  await expect(guide).toHaveCount(0)

  await logout(page)
  const checked = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/me/onboarding'))
  await loginAgain(page, nickname)
  expect(await (await checked).json()).toEqual({ completedAt })
  await page.waitForTimeout(500)
  await expect(parentGuide(page)).toHaveCount(0)
})

test('마지막 단계에서 기기 등록하러 가면 기기 화면으로 가고, 도움말에서 다시 보면 기록은 처음 시각 그대로다', async ({ context, page }) => {
  const nickname = `안내끝${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('guide-finish'))
  await onboardParent(page, nickname, { keepGuide: true })
  const guide = parentGuide(page)
  await guide.getByRole('button', { name: '다음', exact: true }).click()
  await expect(guide.getByRole('heading', { name: '학습 현황과 리포트' })).toBeFocused()
  await guide.getByRole('button', { name: '다음', exact: true }).click()
  await expect(guide.getByRole('heading', { name: '공개 동의는 계정·자녀 설정에서' })).toBeFocused()
  const saved = onboardingPut(page)
  await guide.getByRole('button', { name: '기기 등록하러 가기', exact: true }).click()
  const first = await (await saved).json() as { completedAt: string }
  await page.waitForURL('**/parent/devices**')
  await expect(page.getByRole('form', { name: `${nickname} PIN`, exact: true })).toBeVisible()
  await expect(guide).toHaveCount(0)

  const writes: string[] = []
  page.on('request', r => { if (new URL(r.url()).pathname.endsWith('/me/onboarding') && r.method() !== 'GET') writes.push(r.method()) })
  await page.getByRole('link', { name: '도움말', exact: true }).first().click()
  await page.waitForURL('**/parent/help**')
  await page.getByRole('button', { name: '처음 안내 다시 보기', exact: true }).click()
  await page.waitForURL('**/parent/journal**')
  await expect(guide.getByRole('heading', { name: '먼저 아이 기기를 등록해 주세요' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(guide).toHaveCount(0)
  expect(writes).toEqual([])
  // 새로 불러오면 서버 기록(처음 시각)을 다시 읽고, 안내는 다시 재생하지 않는다.
  const checked = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/me/onboarding'))
  await page.reload()
  expect(await (await checked).json()).toEqual(first)
  await expect(page.getByRole('heading', { name: `${nickname}의 학습 현황` })).toBeVisible()
  await expect(guide).toHaveCount(0)
})
