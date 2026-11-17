import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #705 내 방 바닥·방 소품(사용자 결정 2026-11-17): 방에 관한 것은 모두 내 방 "방 꾸미기" 서랍(벽지·바닥·가구·방 소품, 서랍에서 바로 열기·사기),
// 꾸미기 화면은 화면 테마·캐릭터·옷 입히기만. 방 소품은 바닥·벽 칸에 놓고(core #723) 화살표·초록 칸으로 옮긴다.
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function student(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
}
const menu = (page: Page, name: string) => page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name, exact: true }).click()
const drawer = (page: Page) => page.getByRole('region', { name: '방 꾸미기' })
async function openDrawer(page: Page, tab: string) {
  await page.getByRole('button', { name: '방 꾸미기', exact: true }).click()
  await drawer(page).getByRole('button', { name: tab, exact: true }).click()
}

test('꾸미기는 화면 테마·캐릭터·옷 입히기 세 탭, 방 꾸미기 서랍에 바닥·방 소품, 내 방 아래 칩은 둘 @responsive', async ({ page }) => {
  await student(page)
  await menu(page, '내 방')
  // 넓은 화면은 방 안 아래 칩(이번 주 문제 글자 + 기념 액자 단추), 좁은 화면은 아래 기록 카드(원래 화면)
  if ((page.viewportSize()?.width ?? 0) > 900) await expect(page.locator('.st-room-chips').getByRole('button')).toHaveCount(1)
  await expect(page.getByRole('button', { name: /^꾸미기 →|^뭉치 친구들 →/ })).toHaveCount(0)
  await page.getByRole('button', { name: '방 꾸미기', exact: true }).click()
  await expect(drawer(page).locator('.st-room-drawer-head button')).toHaveText(['액자 걸기', '벽지', '바닥', '가구', '방 소품'])
  await page.getByRole('button', { name: '취소', exact: true }).click()
  await page.getByRole('button', { name: '캐릭터·옷 꾸미기' }).click()
  await expect(page.getByRole('tablist', { name: '꾸미기 종류' }).getByRole('tab')).toHaveText(['화면 테마', '캐릭터', '옷 입히기'])
})

test('서랍에서 바로 열기: 포인트가 모자라면 막히고, 열면 포인트가 줄며 저장해야 방에 반영된다', async ({ page }) => {
  await student(page)
  await menu(page, '내 방')
  await openDrawer(page, '바닥')
  const points = drawer(page).locator('.st-room-points')
  await expect(points).toHaveText('내 포인트 117')
  const save = page.getByRole('button', { name: '저장', exact: true })
  const confirm = drawer(page).locator('section[aria-label="꾸미기 해금 확인"]')
  await drawer(page).getByRole('button', { name: /초록 카펫/ }).click()
  await expect(confirm).toContainText('3포인트가 더 필요해요')
  await expect(confirm.getByRole('button', { name: '포인트로 해금하기' })).toBeDisabled()
  await expect(save).toBeDisabled()
  await confirm.getByRole('button', { name: '취소' }).click()
  await expect(drawer(page).getByText('아직 안 연 것을 골랐어요')).toBeVisible()
  await drawer(page).getByRole('button', { name: /나무 마루/ }).click()
  await confirm.getByRole('button', { name: '포인트로 해금하기' }).click()
  await expect(drawer(page).getByText('열었어요! 저장을 누르면 내 방에 반영돼요.')).toBeVisible()
  await expect(points).toHaveText('내 포인트 57')
  await save.click()
  await expect(page.locator('.st-room-note')).toHaveText('내 방을 저장했어요.')
})

test('방 소품: 서랍에서 사고 놓고 화살표로 옮기며, 못 놓는 자리는 까닭을 알리고, 저장하면 남는다 @responsive', async ({ page }) => {
  await student(page)
  await menu(page, '내 방')
  await openDrawer(page, '방 소품')
  const card = drawer(page).locator('.st-decor-card').filter({ hasText: '작은 화분' })
  await expect(card).toContainText('놓음 0/0')
  await expect(card.getByRole('button', { name: '작은 화분 놓기' })).toBeDisabled()
  await card.getByRole('button', { name: /작은 화분 1개 사기/ }).click()
  const buy = drawer(page).locator('section[aria-label="방 소품 사기 확인"]')
  await expect(buy).toContainText('작은 화분 1개 살까요?')
  await buy.getByRole('button', { name: '포인트로 사기' }).click()
  await expect(drawer(page).getByText('샀어요! 작은 화분이 1개 있어요.')).toBeVisible()
  await expect(card).toContainText('놓음 0/1')

  await card.getByRole('button', { name: '작은 화분 놓기' }).click()
  const move = drawer(page).getByRole('group', { name: '작은 화분 옮기기' })
  await expect(move).toBeVisible()
  await expect(page.locator('.st-decor-cell').first()).toBeAttached() // 놓을 수 있는 초록 칸
  await expect(drawer(page).locator('.st-decor-card')).toHaveCount(0) // 옮기는 동안은 목록을 숨김
  // 색 고르기는 core 색 후속 전까지 숨김
  await expect(drawer(page).getByRole('group', { name: '작은 화분 색' })).toHaveCount(0)
  // 옮기기 판이 열리면 초점은 화살표에, 방향키로도 옮긴다(오른쪽 끝을 넘으면 까닭)
  await expect(move.getByRole('button', { name: '뒤로 한 칸' })).toBeFocused()
  for (let i = 0; i < 20; i++) await page.keyboard.press('ArrowRight')
  await expect(drawer(page).getByRole('alert')).toHaveText('방 끝을 넘어가요.')
  for (let i = 0; i < 8; i++) await page.keyboard.press('ArrowLeft')
  // 뒤로 계속 가면 뭉치 출발 자리나 가구에 막히고 까닭을 알린다
  for (let i = 0; i < 9; i++) await move.getByRole('button', { name: '뒤로 한 칸' }).click()
  await expect(drawer(page).getByRole('alert')).toHaveText(/가구나 창문이 있는 자리예요|뭉치가 서 있는 자리예요|뭉치가 지나갈 길을 막아요/)
  await move.getByRole('button', { name: '오른쪽으로 한 칸' }).click()
  await move.getByRole('button', { name: '다 놓았어요' }).click()
  await expect(card).toContainText('놓음 1/1')
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.locator('.st-room-note')).toHaveText('내 방을 저장했어요.')

  // 다시 열어도 놓인 그대로
  await openDrawer(page, '방 소품')
  await expect(drawer(page).locator('.st-decor-card').filter({ hasText: '작은 화분' })).toContainText('놓음 1/1')
})

test('걸린 액자·놓은 칸 목록을 받기 전에는 방 꾸미기를 열 수 없다(빈 목록으로 저장해 내려가지 않게)', async ({ page }) => {
  await student(page)
  await page.evaluate(() => {
    const orig = window.fetch
    let release: () => void = () => {}
    const gate = new Promise<void>((r) => { release = r })
    ;(window as unknown as { releaseSlots: () => void }).releaseSlots = release
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.includes('/room/frame-slots') && (!init?.method || init.method === 'GET')) await gate
      return orig(input, init)
    }
  })
  await menu(page, '내 방')
  const edit = page.getByRole('button', { name: /방 꾸미기|방을 불러오고 있어요/ })
  await expect(edit).toHaveText('방을 불러오고 있어요')
  await expect(edit).toBeDisabled()
  await page.evaluate(() => (window as unknown as { releaseSlots: () => void }).releaseSlots())
  await expect(edit).toHaveText('방 꾸미기')
  await expect(edit).toBeEnabled()
})

test('좁은 화면: 놓을 때 칸 폭 44px 이상으로 키우고, 화면 밖 소품은 가장자리 화살표, 좌우로 밀어 본다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await student(page)
  await menu(page, '내 방')
  const stageX = () => page.locator('.st-room-stage').evaluate((e) => Number(/translate\((-?[\d.]+)px/.exec(e.style.transform)?.[1] ?? 'NaN'))
  expect(await stageX()).toBe(0) // 처음 화면은 가운데 그대로
  await expect(page.locator('.st-room-album')).toBeHidden() // 폰: 추억 앨범은 방 아래 버튼 줄에서
  await expect(page.locator('.st-room-quick').getByRole('button', { name: '추억의 벽 · 액자' })).toBeVisible()
  await openDrawer(page, '방 소품')
  const card = drawer(page).locator('.st-decor-card').filter({ hasText: '작은 화분' })
  await card.getByRole('button', { name: /작은 화분 1개 사기/ }).click()
  await drawer(page).locator('section[aria-label="방 소품 사기 확인"]').getByRole('button', { name: '포인트로 사기' }).click()
  await card.getByRole('button', { name: '작은 화분 놓기' }).click()
  const widths = await page.locator('.st-decor-cell').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().width))
  expect(widths.length).toBeGreaterThan(0)
  expect(Math.min(...widths)).toBeGreaterThanOrEqual(44)
  // 뒤쪽 줄(오른쪽까지 PC 화면에 보이는 줄)로 간 뒤 오른쪽 끝으로 옮기면 화면이 따라간다
  for (let i = 0; i < 6; i++) await page.keyboard.press('ArrowRight')
  for (let i = 0; i < 6; i++) await page.keyboard.press('ArrowUp')
  for (let i = 0; i < 20; i++) await page.keyboard.press('ArrowRight')
  expect(await stageX()).toBeLessThan(0)
  await drawer(page).getByRole('button', { name: '다 놓았어요' }).click()
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.locator('.st-room-note')).toHaveText('내 방을 저장했어요.')
  // 저장 뒤 처음 화면에서는 오른쪽 끝 소품이 화면 밖 → 화살표
  const right = page.getByRole('button', { name: /오른쪽에 방 소품이 더 있어요/ })
  await expect(right).toBeVisible()
  await right.click()
  await expect(right).toHaveCount(0)
  const pushed = await stageX()
  expect(pushed).toBeLessThan(0)
  // 끌어서 밀기(오른쪽으로 끌면 방 왼쪽이 보임)
  const box = (await page.locator('.st-room-holder').boundingBox())!
  await page.mouse.move(box.x + 120, box.y + box.height * 0.85)
  await page.mouse.down()
  await page.mouse.move(box.x + 260, box.y + box.height * 0.85, { steps: 8 })
  await page.mouse.up()
  expect(await stageX()).toBeGreaterThan(pushed)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('그릴 수 없는 자리에 저장된 방 소품은 방에 그리지 않고 "다시 놓아 주세요", 다시 놓기로 옮긴다', async ({ page }) => {
  await student(page)
  // 서버에는 맞지만(칸 범위 안) 웹에서는 책장 자리라 그릴 수 없는 소품(가구 배치가 바뀐 경우 등, #723)
  await page.evaluate(() => {
    const orig = window.fetch
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.includes('/room/decor-spots') && (!init?.method || init.method === 'GET')) {
        return new Response(JSON.stringify({ spots: [{ surface: 'FLOOR', col: 1, row: 0, itemKey: 'DECOR_PLANT', color: null, name: '작은 화분', assetKey: 'room/decor-plant.svg' }] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return orig(input, init)
    }
  })
  await menu(page, '내 방')
  await openDrawer(page, '방 소품')
  const card = drawer(page).locator('.st-decor-card').filter({ hasText: '작은 화분' })
  await expect(card).toContainText('1개는 다시 놓아 주세요')
  await expect(page.locator('.st-decor-hit')).toHaveCount(0) // 방에 그리지 않으니 누를 자리도 없음
  await card.getByRole('button', { name: '작은 화분 다시 놓기' }).click()
  const move = drawer(page).getByRole('group', { name: '작은 화분 옮기기' })
  await expect(move).toBeVisible()
  await move.getByRole('button', { name: '다 놓았어요' }).click()
  await expect(card).not.toContainText('다시 놓아 주세요')
  await expect(page.locator('.st-decor-hit')).toHaveCount(1)
})

test('방 소품: 취소하면 되돌리고, 저장에 실패하면 놓은 그대로 안내, 다시 들어와도 같은 칸(움직임 줄이기)', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await student(page)
  await page.evaluate(() => {
    const w = window as unknown as { failDecor: boolean }
    w.failDecor = false
    const orig = window.fetch
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (w.failDecor && url.includes('/room/decor-spots') && init?.method === 'PUT') return new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } })
      return orig(input, init)
    }
  })
  await menu(page, '내 방')
  expect(await page.locator('.st-room-world').evaluate((e) => getComputedStyle(e).transitionDuration)).toBe('0s')
  await openDrawer(page, '방 소품')
  const card = () => drawer(page).locator('.st-decor-card').filter({ hasText: '작은 화분' })
  await card().getByRole('button', { name: /작은 화분 1개 사기/ }).click()
  await drawer(page).locator('section[aria-label="방 소품 사기 확인"]').getByRole('button', { name: '포인트로 사기' }).click()
  const place = async () => {
    await card().getByRole('button', { name: '작은 화분 놓기' }).click()
    await drawer(page).getByRole('group', { name: '작은 화분 옮기기' }).getByRole('button', { name: '다 놓았어요' }).click()
    await expect(card()).toContainText('놓음 1/1')
  }
  // 취소: 놓은 것을 되돌린다(산 것은 그대로)
  await place()
  await page.getByRole('button', { name: '취소', exact: true }).click()
  await expect(page.locator('.st-room-note')).toHaveText('바꾼 내용을 취소했어요.')
  await expect(page.locator('[data-decor]')).toHaveCount(0)
  await openDrawer(page, '방 소품')
  await expect(card()).toContainText('놓음 0/1')
  // 저장 실패: 놓은 그대로 두고 안내
  await place()
  await page.evaluate(() => { (window as unknown as { failDecor: boolean }).failDecor = true })
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.getByText('방 소품을 놓지 못했어요. 놓은 그대로 두었으니 잠시 뒤에 다시 저장해 주세요.')).toBeVisible()
  await expect(page.getByRole('button', { name: '취소', exact: true })).toBeVisible()
  await expect(card()).toContainText('놓음 1/1')
  await page.evaluate(() => { (window as unknown as { failDecor: boolean }).failDecor = false })
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.locator('.st-room-note')).toHaveText('내 방을 저장했어요.')
  // 다른 화면에 갔다 와도 같은 칸
  await menu(page, '홈')
  await waitForStudentHome(page)
  await menu(page, '내 방')
  await expect(page.locator('[data-decor]').first()).toBeAttached()
  await openDrawer(page, '방 소품')
  await expect(card()).toContainText('놓음 1/1')
})
