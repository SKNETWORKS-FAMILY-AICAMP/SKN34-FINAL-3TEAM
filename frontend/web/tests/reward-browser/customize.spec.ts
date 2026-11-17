import { waitForStudentHome } from '../browser/studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import type { Equipped, LookItem } from '../../src/domain/retention.ts'
import { baseLookCatalog, NO_EQUIPPED } from '../../src/domain/retention.ts'

// 합성 HTTP 응답. 계약 기준: develop 7a0fb9c9 RewardController/LookUnlockService.
async function rewardServer(page: Page, initialBalance = 300) {
  const state = {
    balance: initialBalance, theme: 'lake', companion: 'mungchi', equipped: { ...NO_EQUIPPED },
    owned: new Set(['THEME:lake', 'COMPANION:mungchi']), catalogFails: false, loseReply: false, lagCatalog: false,
    keys: [] as string[], receipts: new Map<string, { itemKey: string; unlocked: true; balance: number }>(),
    writes: [] as Record<string, unknown>[],
    ledger: Array.from({ length: Math.ceil(initialBalance / 10) }, (_, i) => ({
      eventType: 'MISSION_COMPLETED', amount: Math.min(10, initialBalance - i * 10),
      createdAt: new Date(Date.parse('2026-11-08T12:00:00Z') - i * 60_000).toISOString(),
    })),
  }
  const child = { id: '00000000-0000-4000-8000-000000000001', nickname: '합성 학생', grade: 3, birthYear: 2017 }
  const catalog = (): LookItem[] => [...baseLookCatalog().map(i => ({ ...i, unlocked: state.owned.has(i.itemKey) && !(state.lagCatalog && i.itemKey === 'THEME:forest') })),
    { itemKey: 'HAT_ACORN', slot: 'HAT', name: '도토리 모자', pricePoints: 40, unlocked: state.owned.has('HAT_ACORN'), onSale: true, assetKey: 'looks/hat-acorn.svg', ownedCount: null, createdAt: '2026-11-06T00:00:00Z' },
    { itemKey: 'HAT_CROWN', slot: 'HAT', name: '종이 왕관', pricePoints: 80, unlocked: true, onSale: false, assetKey: 'looks/hat-crown.svg', ownedCount: null, createdAt: '2026-11-06T00:00:00Z' }]
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request(), url = new URL(request.url()), path = decodeURIComponent(url.pathname).replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/auth/student/profiles') return json({ items: [{ childId: child.id, nickname: child.nickname, pinSet: true, pinLocked: false }] })
    if (path === '/auth/student/login') return json({ role: 'STUDENT', accessToken: 'synthetic-student', child: { ...child, childId: child.id } })
    if (path === '/auth/refresh') return json({ status: 401, code: 'UNAUTHENTICATED' }, 401)
    if (path === '/me') return json({ role: 'STUDENT', child, nextAction: 'READY', startPath: '/student/home' })
    if (path === '/students/me/home') return json({ student: child, state: 'NO_RECORD', period: { from: '2026-11-09', to: '2026-11-09' }, missions: [], resume: null })
    if (path === '/students/me/weekly-theme') return json(null)
    if (path === '/students/me/preferences') {
      if (request.method() === 'PUT') {
        const body = request.postDataJSON() as { theme: string; companion: string; equipped?: Equipped }
        state.writes.push(body)
        state.theme = body.theme; state.companion = body.companion
        if (body.equipped) state.equipped = body.equipped
      }
      return json({ theme: state.theme, companion: state.companion, equipped: state.equipped, updatedAt: '2026-11-09T00:00:00Z' })
    }
    if (path === '/students/me/points') {
      const current = Number(url.searchParams.get('page') ?? 0)
      return json({ balance: state.balance, items: state.ledger.slice(current * 20, (current + 1) * 20), page: current, size: 20, totalElements: state.ledger.length })
    }
    if (path === '/students/me/look-items') return state.catalogFails ? json({ status: 503, code: 'UNAVAILABLE', title: '꾸미기 목록 연결 실패' }, 503) : json({ items: catalog() })
    if (path.endsWith('/unlock')) {
      expect(request.method()).toBe('POST'); expect(request.postData()).toBeNull()
      const key = request.headers()['idempotency-key']
      expect(key).toMatch(/^[0-9a-f-]{36}$/)
      state.keys.push(key)
      const old = state.receipts.get(key)
      if (old) { state.lagCatalog = false; return json(old) }
      const itemKey = path.split('/').at(-2)!, item = catalog().find(i => i.itemKey === itemKey)!
      if (!item.onSale && !item.unlocked) return json({ status: 409, code: 'LOOK_ITEM_NOT_ON_SALE' }, 409)
      if (!item.unlocked && state.balance < item.pricePoints) return json({ status: 409, code: 'INSUFFICIENT_POINTS', title: '포인트가 모자라요.' }, 409)
      if (!state.owned.has(itemKey)) {
        state.balance -= item.pricePoints; state.owned.add(itemKey)
        state.ledger.unshift({ eventType: 'UNLOCK', amount: -item.pricePoints, createdAt: '2026-11-09T00:00:00Z' })
      }
      const result = { itemKey, unlocked: true as const, balance: state.balance }
      state.receipts.set(key, result)
      if (state.loseReply) { state.loseReply = false; state.lagCatalog = true; return route.abort('failed') }
      return json(result)
    }
    return json({ status: 404, code: 'NOT_FOUND' }, 404)
  })
  return state
}
async function openCustomize(page: Page) {
  await page.goto('/student/login')
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
  // #648 꾸미기는 전체 화면(/student/customize). 설정 → 내 포인트 보기 → "꾸미기 해금하러 가기"로 연다
  await openPoints(page)
  await page.getByRole('button', { name: '꾸미기 해금하러 가기', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/customize/)
  const screen = page.getByRole('main')
  await expect(screen.getByRole('heading', { name: '나만의 꾸미기', exact: true })).toBeVisible()
  await expect(screen.getByText('내 포인트', { exact: false })).toBeVisible()
  return screen
}
async function openPoints(page: Page) {
  await page.getByRole('button', { name: '설정', exact: true }).click()
  await page.getByRole('button', { name: '내 포인트 보기', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/points/)
}
const tab = (page: Page, name: string) => page.getByRole('tab', { name, exact: true }).click()

test('해금 확인→잔액 갱신→테마·아이템 저장과 판매 중단 보유품 유지', async ({ page }, testInfo) => {
  const state = await rewardServer(page)
  const screen = await openCustomize(page)
  // #648 시안 Customize: 카드는 미리 보기만 바꾸고 아래 버튼이 해금(확인 단계)·저장을 한다
  const forest = screen.getByRole('button', { name: /^생각 숲 생각이 자라는 숲/ })
  await forest.click()
  await expect(forest).toHaveAttribute('aria-pressed', 'true')
  expect(state.writes).toHaveLength(0)
  await screen.getByRole('button', { name: '100포인트로 열기', exact: true }).click()
  expect(state.keys).toHaveLength(0)
  await expect(screen.getByText('100포인트를 써요. 해금 후 200포인트가 남아요.')).toBeVisible()
  await screen.getByRole('button', { name: '포인트로 해금하기', exact: true }).click()
  await expect(screen.getByText('내 포인트 200', { exact: true })).toBeVisible()
  await screen.getByRole('button', { name: '이 테마 쓰기', exact: true }).click()
  await expect(forest).toContainText('쓰는 중')
  expect(state.theme).toBe('forest')
  await tab(page, '옷 입히기')
  const acorn = screen.getByRole('button', { name: /^도토리 모자/ })
  await acorn.click()
  await screen.getByRole('button', { name: '도토리 모자 40포인트로 열기', exact: true }).click()
  await screen.getByRole('button', { name: '포인트로 해금하기', exact: true }).click()
  await screen.getByRole('button', { name: '이대로 입기', exact: true }).click()
  await expect(screen.getByRole('button', { name: '입고 있어요', exact: true })).toBeDisabled()
  await expect(acorn).toHaveAttribute('aria-pressed', 'true')
  await tab(page, '화면 테마')
  const lake = screen.getByRole('button', { name: /^생각 호수 생각이 뭉치는 호수/ })
  await lake.click()
  await screen.getByRole('button', { name: '이 테마 쓰기', exact: true }).click()
  await expect(lake).toHaveAttribute('aria-pressed', 'true')
  await expect(lake).toContainText('쓰는 중')
  await tab(page, '옷 입히기')
  await expect(acorn).toHaveAttribute('aria-pressed', 'true')
  expect(state.writes.at(-1)).not.toHaveProperty('equipped')
  expect(state.equipped.HAT).toBe('HAT_ACORN')
  await expect(screen.getByRole('button', { name: '종이 왕관 가지고 있어요', exact: true })).toBeEnabled()
  await screen.getByRole('button', { name: '내 방', exact: true }).click()
  await expect(page).toHaveURL(/\/student\/room/)
  await openPoints(page) // 내 포인트는 설정의 "내 포인트 보기"(#583·#648)
  await expect(page.getByText('지금 160포인트', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: '다음 내역', exact: true }).click()
  await expect(page.getByText('2 / 2쪽', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '다음 내역', exact: true })).toBeDisabled()
  const out = '.taste-skill/reward-after'
  await mkdir(out, { recursive: true })
  await page.getByRole('button', { name: '꾸미기 해금하러 가기' }).click()
  await page.screenshot({ path: `${out}/${testInfo.project.name}.png`, fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await writeFile(`${out}/${testInfo.project.name}.html`, (await page.content()).replace(/<script\b[\s\S]*?<\/script>/gi, ''))
})

test('잔액 부족은 추가 요청 없이 안내하고 목록 장애는 유료 항목을 선택하지 못하게 한다', async ({ page }) => {
  const state = await rewardServer(page, 20)
  const screen = await openCustomize(page)
  await screen.getByRole('button', { name: /^생각 숲 생각이 자라는 숲/ }).click()
  await screen.getByRole('button', { name: '100포인트로 열기', exact: true }).click()
  await expect(screen.getByText('100포인트를 써요. 80포인트가 더 필요해요.')).toBeVisible()
  await expect(screen.getByRole('button', { name: '포인트로 해금하기' })).toBeDisabled()
  expect(state.keys).toHaveLength(0)
  await screen.getByRole('button', { name: '취소', exact: true }).click()
  await screen.getByRole('button', { name: '내 방', exact: true }).click()
  state.catalogFails = true
  await openPoints(page)
  await page.getByRole('button', { name: '꾸미기 해금하러 가기', exact: true }).click()
  await expect(screen.getByText('꾸미기 목록 연결 실패', { exact: true })).toBeVisible()
  await expect(screen.getByRole('button', { name: /^생각 숲 생각이 자라는 숲/ })).toBeDisabled()
  await expect(screen.getByRole('button', { name: /포인트로 열기$/ })).toHaveCount(0)
})

test('해금 응답 유실 뒤 같은 멱등 키 재시도는 두 번 차감하지 않는다', async ({ page }) => {
  const state = await rewardServer(page), screen = await openCustomize(page)
  state.loseReply = true
  await screen.getByRole('button', { name: /^생각 숲 생각이 자라는 숲/ }).click()
  await screen.getByRole('button', { name: '100포인트로 열기', exact: true }).click()
  await screen.getByRole('button', { name: '포인트로 해금하기', exact: true }).click()
  await expect.poll(() => state.keys.length).toBe(1)
  await expect(screen.getByRole('button', { name: '포인트로 해금하기', exact: true })).toBeEnabled()
  await screen.getByRole('button', { name: '포인트로 해금하기', exact: true }).click()
  await expect(screen.getByRole('button', { name: '이 테마 쓰기', exact: true })).toBeEnabled()
  expect(state.keys).toHaveLength(2); expect(state.keys[0]).toBe(state.keys[1])
  expect(state.balance).toBe(200); expect(state.ledger.filter(e => e.eventType === 'UNLOCK')).toHaveLength(1)
})

// #648·#698 뭉치 친구들 12종: core가 12종을 모두 저장(#697)해 새 7종도 해금·선택한다. 곧 만나요 없음
test('친구 12종 모두 해금·선택하고, 새 친구는 친구 id가 서버 값으로 저장된다', async ({ page }) => {
  const state = await rewardServer(page)
  const screen = await openCustomize(page)
  await tab(page, '캐릭터')
  const buddies = screen.getByRole('region', { name: '누구랑 같이 다닐까?' })
  await expect(buddies.getByRole('button', { name: /곧 만나요$/ })).toHaveCount(0)
  for (const name of ['눈뭉치', '털실뭉치', '별뭉치', '거품뭉치', '종이뭉치', '꽃잎뭉치', '얼음뭉치'])
    await expect(buddies.getByRole('button', { name: new RegExp(`^${name} `) })).toBeEnabled()
  await expect(buddies.getByRole('button', { name: /^솜뭉치 / })).toHaveAttribute('aria-pressed', 'true')
  // 새 친구(눈뭉치): 해금(150) → 함께 다니기 → 서버 값 snow로 저장(#697: 새 7종은 친구 id = 서버 값)
  const snow = buddies.getByRole('button', { name: /^눈뭉치 / })
  await snow.click()
  await expect(snow).toHaveAttribute('aria-pressed', 'true')
  await screen.getByRole('button', { name: '150포인트로 만나기', exact: true }).click()
  await expect(screen.getByRole('heading', { name: '눈뭉치 해금할까요?' })).toBeVisible()
  await screen.getByRole('button', { name: '포인트로 해금하기', exact: true }).click()
  await expect(screen.getByText('내 포인트 150', { exact: true })).toBeVisible()
  await screen.getByRole('button', { name: '함께 다니기', exact: true }).click()
  await expect(snow).toContainText('함께 다니는 중')
  expect(state.writes.at(-1)).toMatchObject({ companion: 'snow' })
  await expect(screen.getByRole('button', { name: '함께 다니는 중', exact: true })).toBeDisabled()
})
