import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #917: 처리 중 단추를 disabled로 끄면 키보드 초점이 body로 빠진다. 관리자 화면은 aria-disabled로 초점을 지키고 중복 제출을 막는다.
// 응답을 늦추려고 fetch를 감싼다(MSW 서비스 워커 앞). 테마 초안 요청은 409를 대신 돌려준다.
async function slowAdminWrites(page: Page) {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    const calls: string[] = []
    Object.assign(window, { __adminWrites: calls })
    window.fetch = async (input, init) => {
      const request = new Request(input, init)
      const path = new URL(request.url).pathname
      if (request.method === 'POST' && /\/api\/v1\/admin\/(look-items|theme-drafts)$/.test(path)) {
        calls.push(path)
        await new Promise(resolve => setTimeout(resolve, 1200))
        if (path.endsWith('/theme-drafts'))
          return new Response(JSON.stringify({ type: 'about:blank', status: 409, code: 'THEME_DRAFT_CONFLICT', title: '이미 생성 중인 초안이 있습니다.' }),
            { status: 409, headers: { 'content-type': 'application/problem+json' } })
      }
      return original(input, init)
    }
  })
}

async function login(page: Page, label: string) {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill('content@example.test')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await expect(page.getByRole('heading', { name: '운영 요약', exact: true })).toBeVisible()
  const menu = page.getByRole('button', { name: '메뉴', exact: true })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('navigation', { name: '관리자 메뉴' }).getByRole('link', { name: label, exact: true }).click()
}

const activeTag = (page: Page) => page.evaluate(() => document.activeElement?.tagName)
const writes = (page: Page) => page.evaluate(() => (window as unknown as { __adminWrites: string[] }).__adminWrites.length)

test('아이템 저장을 키보드로 누르면 처리 중·409 뒤에도 초점이 저장 단추에 남고 오류 글이 보인다 @responsive', async ({ page }) => {
  await slowAdminWrites(page)
  await login(page, '꾸미기 아이템')
  await page.getByRole('button', { name: '새 아이템', exact: true }).click()
  await page.getByLabel('아이템 코드', { exact: true }).fill('FLOOR_PREVIEW')
  await page.getByLabel('아이템 칸', { exact: true }).selectOption('FLOOR')
  await page.getByLabel('아이템 이름', { exact: true }).fill('중복 코드 시험')
  await page.getByLabel('필요 포인트', { exact: true }).fill('30')
  await page.getByLabel('그림 키', { exact: true }).fill('room/floor-grass.png')
  const save = page.getByRole('button', { name: '저장', exact: true })
  await save.focus()
  await page.keyboard.press('Enter')
  // 처리 중 상태(고치기 전에는 disabled)가 된 뒤에도 초점이 body로 빠지지 않는다.
  await expect.poll(() => save.evaluate(b => b.hasAttribute('disabled') || b.getAttribute('aria-disabled') === 'true')).toBe(true)
  expect(await activeTag(page)).toBe('BUTTON')
  await expect(save).toBeFocused()
  await expect(save).toHaveAttribute('aria-disabled', 'true')
  // 처리 중 다시 눌러도 두 번째 요청은 나가지 않는다.
  await page.keyboard.press('Enter')
  await page.keyboard.press('Space')
  const alert = page.getByRole('alert').filter({ hasText: '이미 있는 코드입니다.' })
  await expect(alert).toBeVisible()
  await expect(alert).toBeInViewport()
  await expect(save).not.toHaveAttribute('aria-disabled')
  await expect(save).toBeFocused()
  expect(await activeTag(page)).toBe('BUTTON')
  expect(await writes(page)).toBe(1)
})

test('테마 초안 생성 요청을 키보드로 누르면 처리 중·오류 뒤에도 초점이 단추에 남는다 @responsive', async ({ page }) => {
  await slowAdminWrites(page)
  await login(page, '주간 테마 검수')
  await page.getByRole('button', { name: '테마 추가 생성 요청', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '테마 추가 생성 요청' })
  await dialog.getByLabel('생성 학년').selectOption('G4')
  const request = dialog.getByRole('button', { name: '검수용 초안 만들기', exact: true })
  await request.focus()
  await page.keyboard.press('Enter')
  const pending = dialog.getByRole('button', { name: '요청 중…', exact: true })
  await expect(pending).toHaveText('요청 중…')
  expect(await activeTag(page)).toBe('BUTTON')
  await expect(pending).toBeFocused()
  await expect(pending).toHaveAttribute('aria-disabled', 'true')
  await page.keyboard.press('Enter')
  const alert = page.getByRole('alert').filter({ hasText: '이미 생성 중인 초안이 있습니다.' })
  await expect(alert).toBeVisible()
  await expect(alert).toBeInViewport()
  await expect(request).toBeFocused()
  expect(await activeTag(page)).toBe('BUTTON')
  expect(await writes(page)).toBe(1)
})
