import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function parentLogin(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  await expect(page.getByRole('heading', { name: /의 학습 현황$/ })).toBeVisible()
}

async function navigate(page: Page, name: string) {
  const menu = page.getByRole('button', { name: '학부모 메뉴 열기' })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('link', { name, exact: true }).filter({ visible: true }).click()
}

test('비공개 자녀의 수치·리포트·설정·결제는 이용 가능하고 원문 대화는 요청하지 않는다 @responsive', async ({ page }) => {
  const originals: string[] = [], writes: string[] = []
  page.on('request', request => {
    const path = new URL(request.url()).pathname
    if (/\/children\/[^/]+\/records$|\/conversations$/.test(path)) originals.push(path)
    if (request.method() === 'POST') writes.push(path)
  })
  await parentLogin(page)
  await expect(page.getByRole('region', { name: '기간 요약' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '답변 원문은 아이가 비공개로 두었어요' })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await navigate(page, 'AI 챗봇')
  await expect(page.getByRole('heading', { name: /기록 분석 질문은 잠시/ })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '기록에 대한 질문' })).toHaveCount(0)
  expect(originals).toEqual([])
  await navigate(page, '리포트')
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).first().click()
  await expect(page.getByText('위 학습 수치는 계속 확인할 수 있습니다.', { exact: false }).last()).toBeVisible()
  await expect(page.getByRole('button', { name: 'PDF 다운로드', exact: true })).toBeDisabled()
  await expect(page.getByRole('region', { name: '이 리포트로 AI에게 질문하기' })).toHaveCount(0)
  await navigate(page, '계정·자녀 설정')
  await expect(page.getByLabel('조회 시작일')).toHaveCount(0)
  await expect(page.getByText('학년은 자동으로 바뀌지 않습니다.', { exact: false })).toBeVisible()
  await page.getByRole('tab', { name: '계정 관리', exact: true }).click()
  await expect(page.getByRole('heading', { name: '회원 탈퇴', exact: true })).toBeVisible()
  await expect(page.getByLabel('새 학년', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '탈퇴 절차 시작', exact: true }).click()
  await page.getByRole('button', { name: '구독·환불 상태 먼저 확인', exact: true }).click()
  await expect(page.getByText('처리 중 결제 0건', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: '탈퇴 요청 확정', exact: true })).toBeDisabled()
  await navigate(page, '이용권·결제')
  await expect(page.getByRole('heading', { name: '현재 구독', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '이용권 선택', exact: true })).toHaveCount(0)
  expect(writes.some(path => /\/orders$|\/conversations$/.test(path))).toBe(false)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('보호자 커뮤니티 동의 후 자녀가 공개를 직접 켠다 @responsive', async ({ page }) => {
  await parentLogin(page)
  await navigate(page, '계정·자녀 설정')
  await page.getByRole('tab', { name: '공개·동의', exact: true }).click()
  const consent = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/me/consents')
  await page.getByRole('button', { name: '커뮤니티 이용에 동의', exact: true }).click()
  const body = (await consent).postDataJSON()
  expect(body.childId).toBeTruthy()
  expect(body.consents).toEqual([expect.objectContaining({ agreed: true })])
  await expect(page.getByRole('button', { name: '커뮤니티 동의 철회', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '이 자녀로 학습 시작', exact: true }).filter({ visible: true }).click()
  await expect(page).toHaveURL(/\/student\/home/)
  await page.getByRole('button', { name: '공개 설정', exact: true }).click()
  const sharing = page.getByRole('radio', { name: '친구들에게 보여 줄게요', exact: true })
  await expect(sharing).toBeEnabled()
  await expect(sharing).not.toBeChecked()
  const request = page.waitForRequest(r => r.method() === 'PUT' && r.url().endsWith('/students/me/community-settings'))
  await sharing.click()
  await expect(sharing).toBeChecked()
  expect((await request).postDataJSON()).toEqual({ enabled: true })
  await expect(page.getByText('친구 공개 켜짐', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('동의 전 공개는 설명을 열고 상태 갱신 후에만 선택할 수 있다 @responsive', async ({ page }) => {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await expect(page).toHaveURL(/\/student\/home/)
  await expect(page.locator('.st-today')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.getByRole('button', { name: '공개 설정', exact: true }).click()
  const sharing = page.getByRole('radio', { name: '친구들에게 보여 줄게요', exact: true })
  await expect(sharing).toBeDisabled()
  await page.getByRole('button', { name: '보호자 동의 방법 보기', exact: true }).click()
  const guide = page.getByRole('dialog', { name: '친구 공개를 켜려면', exact: true })
  await expect(guide).toBeVisible()
  await expect(guide.getByText('공개·동의', { exact: false })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(guide).toHaveCount(0)
  // 보호자가 다른 기기에서 동의한 뒤의 서버 응답. 새로고침만으로 공개되지는 않는다.
  await page.evaluate(async () => {
    const retentionPath = '/src/mocks/fixtures/retention.ts', studentPath = '/src/mocks/fixtures/studentPinDemo.ts'
    const { setConsent } = await import(retentionPath)
    const { pinDemoChild } = await import(studentPath)
    setConsent(pinDemoChild.id, true)
  })
  await page.getByRole('button', { name: '동의 상태 다시 확인', exact: true }).click()
  await expect(sharing).toBeEnabled()
  await expect(sharing).not.toBeChecked()
  await expect(page.getByText('인증 토큰은 메모리에만 보관합니다.', { exact: false })).toHaveCount(0)
})
