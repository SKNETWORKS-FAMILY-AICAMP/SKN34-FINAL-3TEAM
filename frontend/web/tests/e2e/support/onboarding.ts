import { expect, type Page } from '@playwright/test'
import type { ConsentDocument } from '../../../src/domain/parent.ts'

/** 학부모 첫 사용 안내(#1037) 창 */
export const parentGuide = (page: Page) => page.getByRole('dialog', { name: '학부모 첫 사용 안내' })

/**
 * 학부모 Google 로그인 → 현재 시행 중인 필수 문서 동의 → 자녀 등록(기본 초3) → 대시보드.
 * 대시보드에 처음 뜨는 첫 사용 안내는 기본으로 건너뛴다(완료 기록 저장). keepGuide면 안내를 띄운 채 돌려준다.
 */
export async function onboardParent(page: Page, nickname: string, { grade = 3, keepGuide = false }: { grade?: 3 | 5; keepGuide?: boolean } = {}) {
  await page.goto('/login')
  const documentsLoaded = page.waitForResponse('**/api/v1/consent-documents')
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await page.waitForURL('**/parent/onboarding**')
  const response = await documentsLoaded
  expect(response.ok()).toBe(true)
  const { items } = await response.json() as { items: ConsentDocument[] }
  // #388(V31)부터 선택 동의 COMMUNITY도 함께 온다. 필수 문서는 그대로 세 종류다
  expect(items.filter((document) => document.required).map((document) => document.kind).sort())
    .toEqual(['GUARDIAN', 'PRIVACY', 'TERMS'])
  expect(items.filter((document) => !document.required).map((document) => document.kind)).toEqual(['COMMUNITY'])

  // V25 이후에는 합성 시드보다 최신인 공식 문서가 선택된다. 현재 응답의 제목으로 실제 체크박스를 찾는다.
  async function agree(kind: ConsentDocument['kind']) {
    const document = items.find((item) => item.kind === kind)!
    expect(document.required).toBe(true)
    await page.getByRole('checkbox', { name: `${document.title}에 동의합니다.`, exact: true }).check()
  }
  await agree('TERMS')
  await agree('PRIVACY')
  await page.getByRole('button', { name: '동의 저장하고 계속하기' }).click()
  await page.getByLabel('자녀 별명').fill(nickname)
  await page.getByLabel('자녀 학년').selectOption(String(grade))
  await page.getByLabel('출생연도').selectOption(grade === 3 ? '2017' : '2015')
  await agree('GUARDIAN')
  await page.getByRole('button', { name: '자녀 등록하기' }).click()
  await page.waitForURL('**/parent/journal**')
  await expect(page.getByRole('heading', { name: `${nickname}의 학습 현황` })).toBeVisible()
  await expect(parentGuide(page)).toBeVisible()
  if (keepGuide) return
  const saved = page.waitForResponse(r => r.request().method() === 'PUT' && new URL(r.url()).pathname.endsWith('/me/onboarding'))
  await parentGuide(page).getByRole('button', { name: '건너뛰기', exact: true }).click()
  expect((await saved).ok()).toBe(true)
  await expect(parentGuide(page)).toHaveCount(0)
}
