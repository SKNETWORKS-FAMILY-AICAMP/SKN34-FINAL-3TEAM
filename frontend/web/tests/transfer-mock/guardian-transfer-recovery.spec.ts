import { test, expect, type Page } from '@playwright/test'

const transferId = '73000000-0000-4000-8000-000000000307'
async function proof(page: Page) {
  const section = page.getByRole('region', { name: '탈퇴 최종 확인' })
  const popupEvent = page.waitForEvent('popup')
  await section.getByRole('button', { name: 'Google 본인 확인', exact: true }).click()
  const popup = await popupEvent
  await expect(section.getByRole('button', { name: '완료 확인', exact: true })).toBeVisible()
  await popup.close()
  await section.getByRole('button', { name: '완료 확인', exact: true }).click()
  await expect(section.getByText('재확인을 마쳤습니다.', { exact: false })).toBeVisible()
}
async function pending(page: Page, consentMissing: boolean) {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  // 기능을 끄기 전에 생성되어 남아 있는 요청을 재현한다. 실제 서버·DB는 사용하지 않는다.
  await page.evaluate(async ({ id, revoke }) => {
    const transfersPath = '/src/mocks/fixtures/guardianTransfers.ts'
    const accountsPath = '/src/mocks/fixtures/accounts.ts'
    const { mockTransfers } = await import(transfersPath)
    const { mockConsentHistory } = await import(accountsPath)
    mockTransfers.set(id, { id, childId: 'demo-doyun', childName: '도윤', sender: 'parent@example.test', recipient: 'receiver@example.test', senderName: '발신자', recipientName: '수신자', recipientEmail: 'receiver@example.test', includeConversations: false, status: 'PENDING', createdAt: new Date().toISOString(), resolvedAt: null })
    if (revoke) {
      mockConsentHistory.set('parent@example.test', [])
      window.dispatchEvent(new Event('sagomungchi:consent-required'))
    }
  }, { id: transferId, revoke: consentMissing })
  if (consentMissing) {
    await expect(page).toHaveURL(/\/parent\/onboarding/)
    await page.getByRole('link', { name: '계정 관리', exact: true }).click()
  } else {
    await page.getByRole('link', { name: '계정·자녀 설정', exact: true }).click()
    await page.getByRole('tab', { name: '계정 관리', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '계정·자녀 설정', exact: true })).toBeVisible()
}
async function state(page: Page) {
  return page.evaluate(async id => {
    const path = '/src/mocks/fixtures/guardianTransfers.ts'
    return (await import(path)).mockTransfers.get(id).status as string
  }, transferId)
}

for (const consentMissing of [true, false]) test(`이관 회복: 동의 누락 ${consentMissing}, 유지·취소 후 최종 탈퇴 확인`, async ({ page }) => {
  await pending(page, consentMissing)
  let withdrawals = 0
  page.on('request', r => { if (r.method() === 'POST' && new URL(r.url()).pathname === '/api/v1/me/withdrawal') withdrawals++ })
  await page.getByRole('button', { name: '탈퇴 절차 시작', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '진행 중인 이관 요청' })
  await dialog.getByRole('button', { name: '이관 유지', exact: true }).click()
  expect(await state(page)).toBe('PENDING')
  expect(withdrawals).toBe(0)
  await page.getByRole('button', { name: '탈퇴 절차 시작', exact: true }).click()
  await dialog.getByRole('button', { name: '이관 취소 후 탈퇴 절차 진행', exact: true }).click()
  await expect.poll(() => state(page)).toBe('CANCELLED')
  expect(withdrawals).toBe(0)
  if (!consentMissing && process.env.VITE_GUARDIAN_TRANSFER_ENABLED !== 'false')
    await page.getByRole('button', { name: '이관하지 않고 탈퇴 절차 진행' }).click()
  await page.getByRole('button', { name: '구독·환불 상태 먼저 확인' }).click()
  await expect(page.getByRole('button', { name: '탈퇴 요청 확정', exact: true })).toBeDisabled()
  await proof(page)
  await page.getByRole('checkbox', { name: '계정과 자녀 정보에 미치는 영향을 확인했습니다.' }).check()
  await page.getByRole('button', { name: '탈퇴 요청 확정', exact: true }).click()
  await expect(page).toHaveURL(/\/withdrawal-status/)
  expect(withdrawals).toBe(1)
})

test('이관 회복: 동의 없는 학부모는 목록·취소만 사용하고 신규 이관 UI를 보지 않는다', async ({ page }) => {
  await pending(page, true)
  await page.getByRole('link', { name: '자녀 이관 · 받은 요청 확인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/transfers/)
  await expect(page.getByRole('heading', { name: '보낸 요청 · 수락 대기' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '이관 요청 보내기' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '수락 내용 확인' })).toHaveCount(0)
  await page.getByRole('button', { name: '상태 새로 확인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/transfers/)
  await page.getByRole('button', { name: '이관 요청 취소', exact: true }).click()
  await expect(page.getByRole('heading', { name: '보낸 요청 · 취소됨' })).toBeVisible()
  expect(await state(page)).toBe('CANCELLED')
})
