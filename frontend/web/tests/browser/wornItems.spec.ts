import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

// #455·#557 착용 그림 연결: 그림 키 파일이 있으면 겹쳐 그리고, 없으면 그 칸만 빼고 기본 모습.
// 2026-11-16부터 설계 캔버스 Mungchi의 착용 그림이 public/student-assets/looks에 있다(시험용 합성 그림을 만들던 단계를 지움).
// 파일이 없는 칸은 목업 아이템의 그림 키를 없는 파일로 바꿔 확인한다.
test('착용한 모자 그림 파일이 있으면 홈·내 방 캐릭터에 그리고, 그림 파일이 없는 옷 칸은 그리지 않는다 @responsive', async ({ page }) => {
  await page.goto('/student/login')
  // 로그인 전에 시연 학생(PIN 시연 고정 ID)의 착용을 정해 둔다(새로고침하면 학생 세션이 풀려서)
  await page.evaluate(async () => {
    const { mockLooks, persistLooks } = await import('/src/mocks/fixtures/studentLook.ts' as string)
    const { pinDemoChild } = await import('/src/mocks/fixtures/studentPinDemo.ts' as string)
    const { retentionState, persistRetention } = await import('/src/mocks/fixtures/retention.ts' as string)
    const rain = retentionState.items.find((i: { code: string }) => i.code === 'OUTFIT_RAIN')
    rain.assetKey = 'looks/outfit-not-drawn-yet.svg'
    persistRetention()
    const look = mockLooks.get(pinDemoChild.id) ?? { theme: 'lake', companion: 'mungchi' }
    mockLooks.set(pinDemoChild.id, { ...look, equipped: { HAT: 'HAT_ACORN', OUTFIT: 'OUTFIT_RAIN', ACCESSORY: null, BACKGROUND: null } })
    persistLooks()
  })
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
  const home = page.locator('svg.st-companion').first()
  await expect(home.locator('image[data-slot="HAT"]')).toHaveAttribute('href', '/student-assets/looks/hat-acorn.svg')
  await page.getByRole('button', { name: '내 방', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/room/)
  const room = page.locator('.st-room-char svg.st-companion')
  await expect(room.locator('image[data-slot="HAT"]')).toBeVisible()
  await expect(room.locator('image[data-slot="OUTFIT"]')).toHaveCount(0)
})
