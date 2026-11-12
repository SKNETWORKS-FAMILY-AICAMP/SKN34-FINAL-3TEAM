import { enterStudentFixture } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #433 친구 공개(커뮤니티) 보호자 동의 안내: MSW 앱 화면에서 동의 없음·재동의 대상·동의 후 공개 켜기를 확인한다.
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function parentLogin(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await expect(page.getByLabel('자녀 선택')).not.toHaveValue('')
}

async function studentLogin(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await expect(page).toHaveURL(/\/student\/home/)
}

const friendsOption = (page: Page) => page.getByRole('radio', { name: /친구들에게 보여 줄게요/ })

test('동의 없음: 친구 공개 선택지 옆에 보호자 동의가 필요하다고 보인다 @responsive', async ({ page }) => {
  await studentLogin(page)
  await page.getByRole('button', { name: '설정', exact: true }).click()
  const section = page.getByRole('region', { name: '친구들에게 내 답 보여 주기' })
  await expect(friendsOption(page)).toBeDisabled()
  await expect(section.getByText('· 보호자 동의가 필요해요')).toBeVisible()
  await expect(section.getByRole('note')).toContainText('계정·자녀 설정 › 공개·동의 › 풀이 공유 커뮤니티')
  await expect(friendsOption(page)).toHaveAttribute('aria-describedby', 'community-consent-note')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('동의 후 공개 켜기: 대시보드 링크로 동의하고 자녀 화면에서 친구 공개를 켠다', async ({ page }) => {
  await parentLogin(page)
  const card = page.getByRole('region', { name: /참여 기록/ })
  await expect(card.getByRole('note')).toContainText('아직 동의하지 않아')
  await card.getByRole('link', { name: '커뮤니티 동의하기' }).click()
  await expect(page).toHaveURL(/\/parent\/settings\?.*childId=.*#community-consent$/)
  const consent = page.locator('#community-consent')
  await expect(consent).toBeInViewport()
  await expect(consent.getByRole('status')).toContainText('동의하지 않음')
  await consent.getByRole('button', { name: '커뮤니티 이용에 동의' }).click()
  await expect(consent.getByRole('status')).toContainText('동의함')

  await enterStudentFixture(page)
  await expect(page).toHaveURL(/\/student\/home/)
  await page.getByRole('button', { name: '설정', exact: true }).click()
  const section = page.getByRole('region', { name: '친구들에게 내 답 보여 주기' })
  await expect(friendsOption(page)).toBeEnabled()
  await expect(section.getByText('보호자 동의가 필요해요')).toHaveCount(0)
  await friendsOption(page).click()
  await expect(friendsOption(page)).toBeChecked()
})

test('재동의 대상: 커뮤니티 동의 영역을 숨기지 않고 법정대리인 동의를 먼저 안내한다', async ({ page }) => {
  await parentLogin(page)
  const menu = page.getByRole('button', { name: '학부모 메뉴 열기' })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('link', { name: '계정·자녀 설정', exact: true }).filter({ visible: true }).click()
  await page.getByRole('tab', { name: '공개·동의', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/settings/)
  const consent = page.locator('#community-consent')
  await expect(consent.getByRole('button', { name: '커뮤니티 이용에 동의' })).toBeVisible()
  await page.getByRole('button', { name: '법정대리인 동의 철회' }).first().click()
  await expect(page.getByRole('heading', { name: /법정대리인 재동의/ })).toBeVisible()
  await expect(consent.getByRole('note')).toContainText('법정대리인 동의를 먼저 마쳐 주세요')
  await expect(consent.getByRole('button', { name: '커뮤니티 이용에 동의' })).toHaveCount(0)
})
