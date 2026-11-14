import { existsSync, rmSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'

// MSW 서비스 워커를 거치는 그림 요청은 page.route로 가로채지 못해 시험용 그림 파일을 잠깐 둔다.
// 진짜 그림이 이미 있으면 그대로 쓰고 지우지 않는다.
const hat = fileURLToPath(new URL('../../public/student-assets/looks/hat-acorn.svg', import.meta.url))
const created = !existsSync(hat)
test.beforeAll(() => {
  if (created) writeFileSync(hat, '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60"><circle cx="30" cy="30" r="20" fill="#9c6a3e"/></svg>')
})
test.afterAll(() => { if (created) rmSync(hat, { force: true }) })
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

// #455·#557 착용 그림 연결: 그림 키 파일이 있으면 겹쳐 그리고, 없으면 그 칸만 빼고 기본 모습.
// 실제 그림은 아직 없어 시험용 합성 SVG를 쓴다. 옷 그림(outfit-rain.svg)은 없는 상태 그대로.
test('착용한 모자 그림 파일이 있으면 내 방·생각 지도 캐릭터에 그리고, 파일이 없는 옷 칸은 그리지 않는다 @responsive', async ({ page }) => {
  await page.goto('/student/login')
  // 로그인 전에 시연 학생(PIN 시연 고정 ID)의 착용을 정해 둔다(새로고침하면 학생 세션이 풀려서)
  await page.evaluate(async () => {
    const { mockLooks, persistLooks } = await import('/src/mocks/fixtures/studentLook.ts' as string)
    const { pinDemoChild } = await import('/src/mocks/fixtures/studentPinDemo.ts' as string)
    const look = mockLooks.get(pinDemoChild.id) ?? { theme: 'lake', companion: 'mungchi' }
    mockLooks.set(pinDemoChild.id, { ...look, equipped: { HAT: 'HAT_ACORN', OUTFIT: 'OUTFIT_RAIN', ACCESSORY: null, BACKGROUND: null } })
    persistLooks()
  })
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await expect(page).toHaveURL(/\/student\/home/)
  const home = page.locator('svg.st-companion').first()
  await expect(home.locator('image[data-slot="HAT"]')).toHaveAttribute('href', '/student-assets/looks/hat-acorn.svg')
  await page.getByRole('button', { name: '내 방', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/room/)
  const room = page.locator('.st-room-art svg.st-companion')
  await expect(room.locator('image[data-slot="HAT"]')).toBeVisible()
  await expect(room.locator('image[data-slot="OUTFIT"]')).toHaveCount(0)
})
