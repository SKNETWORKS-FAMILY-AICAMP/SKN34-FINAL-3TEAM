import { test, expect, type Page } from '@playwright/test'

// 학부모 첫 사용 안내(#1037). MSW 완료 기록은 새 브라우저(sessionStorage)마다 미완료로 시작한다.
test.beforeEach(() => test.skip(test.info().project.name !== 'laptop', '화면 크기는 시험 안에서 바꾸므로 한 프로젝트에서만'))

async function login(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page).toHaveURL(/parent\/journal/)
}
const guide = (page: Page) => page.getByRole('dialog', { name: '학부모 첫 사용 안내' })
const marked = (page: Page) => page.locator('[data-parent-guide-target]')

test('3단계를 넘기고 마지막에 기기 화면으로 가면 다시 뜨지 않는다', async ({ page }, info) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message))
  await login(page)
  const card = guide(page)
  await expect(card).toBeVisible()
  await expect(card.getByRole('heading', { name: '먼저 아이 기기를 등록해 주세요' })).toBeFocused()
  await expect(card).toContainText('QR을 찍고 PIN을 정하면 아이가 바로 시작할 수 있습니다.')
  await expect(card).toContainText("왼쪽 메뉴의 '기기·PIN'입니다.")
  await expect(marked(page)).toHaveCount(1)
  await expect(marked(page)).toHaveText('기기·PIN')
  for (const button of await card.getByRole('button').all()) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  // 안내는 강조 메뉴 오른쪽에 두고 화면 안에 들어온다.
  const menu = (await marked(page).boundingBox())!, box = (await card.boundingBox())!, view = page.viewportSize()!
  expect(box.x).toBeGreaterThanOrEqual(menu.x + menu.width)
  expect(box.y + box.height).toBeLessThanOrEqual(view.height)
  await page.screenshot({ path: info.outputPath('step1.png') })

  await card.getByRole('button', { name: '다음', exact: true }).click()
  await expect(card.getByRole('heading', { name: '학습 현황과 리포트' })).toBeFocused()
  await expect(card).toContainText('2 / 3')
  await expect(marked(page)).toHaveText(['학습 현황', '리포트·기록에 물어보기'])

  await card.getByRole('button', { name: '다음', exact: true }).click()
  await expect(card.getByRole('heading', { name: '공개 동의는 계정·자녀 설정에서' })).toBeFocused()
  await expect(marked(page)).toHaveText('계정·자녀 설정')
  await expect(card.getByRole('button', { name: '건너뛰기' })).toHaveCount(0)
  await expect(card.getByRole('button', { name: '나중에', exact: true })).toBeVisible()
  const saved = page.waitForResponse(r => r.url().endsWith('/api/v1/me/onboarding') && r.request().method() === 'PUT')
  await card.getByRole('button', { name: '기기 등록하러 가기', exact: true }).click()
  expect((await saved).ok()).toBe(true)
  await expect(page).toHaveURL(/\/parent\/devices\?childId=/)
  await expect(guide(page)).toHaveCount(0)
  await expect(marked(page)).toHaveCount(0)

  await page.goto('/parent/journal')
  await expect(page.getByRole('heading', { name: /의 학습 현황$/ })).toBeVisible()
  await page.waitForTimeout(300)
  await expect(guide(page)).toHaveCount(0)
  expect(errors).toEqual([])
})

test('Esc로 건너뛰면 완료로 기록하고, 도움말에서 다시 보면 기록은 그대로 둔다', async ({ page }) => {
  await login(page)
  await expect(guide(page)).toBeVisible()
  const saved = page.waitForResponse(r => r.url().endsWith('/api/v1/me/onboarding') && r.request().method() === 'PUT')
  await page.keyboard.press('Escape')
  expect(((await (await saved).json()) as { completedAt: unknown }).completedAt).toEqual(expect.any(String))
  await expect(guide(page)).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: /의 학습 현황$/ })).toBeVisible()
  await expect(guide(page)).toHaveCount(0)

  await page.locator('.ws-side').getByRole('link', { name: '도움말' }).click()
  await expect(page).toHaveURL(/\/parent\/help/)
  const puts: string[] = []
  page.on('request', r => { if (r.url().endsWith('/api/v1/me/onboarding') && r.method() !== 'GET') puts.push(r.method()) })
  await page.getByRole('button', { name: '처음 안내 다시 보기' }).click()
  await expect(page).toHaveURL(/\/parent\/journal\?childId=/)
  const card = guide(page)
  await expect(card.getByRole('heading', { name: '먼저 아이 기기를 등록해 주세요' })).toBeFocused()
  await card.getByRole('button', { name: '건너뛰기' }).click()
  await expect(card).toHaveCount(0)
  expect(puts).toEqual([])
  // 다시 보기 뒤 새로고침해도 다시 재생하지 않는다.
  await page.reload()
  await expect(page.getByRole('heading', { name: /의 학습 현황$/ })).toBeVisible()
  await expect(guide(page)).toHaveCount(0)
})

test('좁은 화면: 접힌 메뉴는 위치를 말로, 폰 하단 바는 짧은 이름으로 안내한다', async ({ page }, info) => {
  await page.setViewportSize({ width: 1024, height: 768 })
  await login(page)
  const card = guide(page)
  await expect(card).toContainText("화면 위 '메뉴'를 열면 '기기·PIN'이 있어요.")
  await expect(marked(page)).toHaveText('메뉴')
  await page.screenshot({ path: info.outputPath('collapsed.png') })
  // 메뉴 창을 열면 창 안의 메뉴를 강조하고, Esc는 메뉴 창부터 닫는다.
  await page.getByRole('button', { name: '학부모 메뉴 열기' }).click()
  const menu = page.getByRole('dialog', { name: '학부모 메뉴' })
  await expect(menu.locator('[data-parent-guide-target]')).toHaveText('기기·PIN')
  await page.keyboard.press('Escape')
  await expect(menu).toHaveCount(0)
  await expect(card).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(card).toContainText("화면 아래 메뉴의 '기기'입니다.")
  await expect(page.locator('.ws-bottom-nav [data-parent-guide-target]')).toHaveCount(1)
  const box = (await card.boundingBox())!, nav = (await page.locator('.ws-bottom-nav').boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(390)
  expect(box.y + box.height).toBeLessThanOrEqual(nav.y)
  await card.getByRole('button', { name: '다음', exact: true }).click()
  await expect(card).toContainText("화면 아래 메뉴의 '학습'·'리포트'입니다.")
  await page.screenshot({ path: info.outputPath('compact.png') })
  await card.getByRole('button', { name: '건너뛰기' }).click()
  await expect(card).toHaveCount(0)
})
