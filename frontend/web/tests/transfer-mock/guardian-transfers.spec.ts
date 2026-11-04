import { test, expect, type Page, type Locator } from '@playwright/test'

async function login(page: Page, email: string) {
  await page.getByRole('textbox', { name: '이메일', exact: true }).fill(email)
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\//)
}
async function openTransfers(page: Page) {
  await page.getByRole('link', { name: '계정·자녀 관리', exact: true }).click()
  await page.getByRole('link', { name: '자녀 이관 · 받은 요청 확인' }).click()
  await expect(page.getByRole('heading', { name: '자녀 이관', exact: true })).toBeVisible()
}
async function proof(page: Page, dialog: Locator) {
  const popupEvent = page.waitForEvent('popup')
  await dialog.getByRole('button', { name: 'Google 본인 확인', exact: true }).click()
  const popup = await popupEvent
  await expect(dialog.getByRole('button', { name: '완료 확인', exact: true })).toBeVisible()
  await popup.close()
  await dialog.getByRole('button', { name: '완료 확인', exact: true }).click()
  await expect(dialog.getByText('재확인을 마쳤습니다.', { exact: false })).toBeVisible()
}
async function send(page: Page) {
  await page.getByLabel('받는 학부모의 가입 이메일').fill('receiver@example.test')
  await page.getByRole('button', { name: '학부모 찾기', exact: true }).click()
  await page.getByRole('button', { name: '이관 내용 확인', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '자녀 이관을 요청하시겠습니까?' })
  await expect(dialog.getByRole('checkbox')).not.toBeChecked()
  await proof(page, dialog)
  await dialog.getByRole('button', { name: '이관 요청', exact: true }).click()
  await expect(page.getByRole('heading', { name: '보낸 요청 · 수락 대기' })).toBeVisible()
}
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/login')
  await login(page, 'parent@example.test')
  // 기존 합성 계정의 PREMIUM 시나리오만 FREE로 바꿔 금융 정리 완료 상태에서 시작한다.
  await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/childPlan.ts'
    const { setMockChildPlan } = await import(path)
    if (!setMockChildPlan({ childId: 'demo-seoyun', plan: 'FREE' })) throw new Error('합성 계정 준비 실패')
  })
  await openTransfers(page)
})

test('MSW 화면: 3명 한도 팝업, 요청 후 자녀 없는 학부모의 동의·수락', async ({ page }, info) => {
  await page.getByLabel('받는 학부모의 가입 이메일').fill('full@example.test')
  await page.getByRole('button', { name: '학부모 찾기', exact: true }).click()
  const limit = page.getByRole('dialog', { name: '자녀 등록 한도' })
  await expect(limit).toContainText('3명')
  await limit.getByRole('button', { name: '확인', exact: true }).click()
  await send(page)
  await page.getByRole('button', { name: '로그아웃', exact: true }).click()
  await login(page, 'receiver@example.test')
  await openTransfers(page)
  await expect(page.getByText('등록된 자녀가 없어도 아래에서 받은 요청을 수락할 수 있습니다.')).toBeVisible()
  await page.getByRole('button', { name: '수락 내용 확인' }).click()
  const dialog = page.getByRole('dialog', { name: '자녀 이관 수락', exact: true })
  await expect(dialog.getByRole('button', { name: '동의하고 수락' })).toBeDisabled()
  await dialog.getByRole('checkbox', { name: /동의합니다/ }).check()
  await proof(page, dialog)
  await dialog.getByRole('button', { name: '동의하고 수락' }).click()
  await expect(page.getByRole('heading', { name: '받은 요청 · 이관 완료' })).toBeVisible()
  await expect(page.getByLabel('이관할 자녀')).toContainText('서윤')
  await page.screenshot({ path: info.outputPath('transfer-accepted.png'), fullPage: true })
  await page.getByRole('button', { name: '로그아웃', exact: true }).click()
  await login(page, 'parent@example.test')
  await openTransfers(page)
  await expect(page.getByRole('heading', { name: '보낸 요청 · 이관 완료' })).toBeVisible()
  await expect(page.getByLabel('이관할 자녀')).not.toContainText('서윤')
})

test('MSW 화면: 발신자 취소와 수신자 거절 후 자녀 연결 유지', async ({ page }) => {
  await send(page)
  await page.getByRole('button', { name: '이관 요청 취소' }).click()
  await expect(page.getByRole('heading', { name: '보낸 요청 · 취소됨' })).toBeVisible()
  await send(page)
  await page.getByRole('button', { name: '로그아웃', exact: true }).click()
  await login(page, 'receiver@example.test')
  await openTransfers(page)
  await page.getByRole('button', { name: '거절', exact: true }).click()
  await expect(page.getByRole('heading', { name: '받은 요청 · 거절됨' })).toBeVisible()
  await expect(page.getByText('등록된 자녀가 없어도 아래에서 받은 요청을 수락할 수 있습니다.')).toBeVisible()
})
