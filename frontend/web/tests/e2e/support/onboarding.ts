import { expect, type Page } from '@playwright/test'

/** 학부모 Google 로그인 → 필수 동의 → 자녀 등록(초3) → 대시보드. 시드 문서: tests/e2e/seed/core.sql */
export async function onboardParent(page: Page, nickname: string) {
  await page.goto('/login')
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL('**/parent/onboarding**')
  await page.getByLabel('E2E 이용약관에 동의합니다.').check()
  await page.getByLabel('E2E 개인정보 처리방침에 동의합니다.').check()
  await page.getByRole('button', { name: '동의 저장하고 계속하기' }).click()
  await page.getByLabel('자녀 별명').fill(nickname)
  await page.getByLabel('자녀 학년').selectOption('3')
  await page.getByLabel('출생연도').fill('2017')
  await page.getByLabel('E2E 보호자 동의에 동의합니다.').check()
  await page.getByRole('button', { name: '자녀 등록하기' }).click()
  await page.waitForURL('**/parent/journal**')
  await expect(page.getByRole('heading', { name: `${nickname}의 학습 기록` })).toBeVisible()
}
