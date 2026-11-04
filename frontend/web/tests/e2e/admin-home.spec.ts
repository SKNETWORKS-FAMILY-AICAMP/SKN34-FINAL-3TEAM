import { expect, test } from '@playwright/test'
import { admin, useGoogleIdentity } from './support/google.ts'

test('관리자 Google 로그인 → 운영 현황', async ({ context, page }) => {
  await useGoogleIdentity(context, admin)
  await page.goto('/admin/login')
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL('**/admin/home**')
  await expect(page.getByRole('heading', { name: '운영 요약' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '운영 현황' })).toBeVisible()
  await expect(page.getByText(/실제 집계 기간 · \d{4}-\d{2}-\d{2} ~ \d{4}-\d{2}-\d{2}/)).toBeVisible()
  await expect(page.getByRole('heading', { name: '학습 시도' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '처리 현황' })).toBeVisible()
  await expect(page.getByRole('link', { name: '운영 현황' })).toHaveAttribute('aria-current', 'page')
})
