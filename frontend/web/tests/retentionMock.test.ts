import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { retentionHandlers } from '../src/mocks/handlers/retention.ts'
import { serviceHandlers } from '../src/mocks/handlers/service.ts'
import { parentHandlers } from '../src/mocks/handlers/parent.ts'
import { adminHandlers } from '../src/mocks/handlers/admin.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { balanceOf, MOCK_STORY, MOCK_WEEKDAY_KEY, resetRetention, retentionState, themeMissions, weekStart, weeklyThemeFor } from '../src/mocks/fixtures/retention.ts'
import type { Mission } from '../src/domain/classroom.ts'
import { THEME_DAYS } from '../src/domain/retention.ts'
import { THINKING_ORDER } from '../src/domain/studentLook.ts'
import { saveSharing } from '../src/mocks/fixtures/sharing.ts'
import { setMockChildPlan } from '../src/mocks/fixtures/childPlan.ts'
import { mockPremium } from '../src/mocks/fixtures/payments.ts'
import { fixtureStore } from '../src/mocks/fixtures/student.ts'
import { missions as adminMissions } from '../src/mocks/fixtures/admin/operations.ts'

// 2026-11-06 결정(에픽 #396) 참여 기능 목업 계약: API 명세 2.4·2.5·2.8~2.11 구현 예정 경로.
const handlers = [...retentionHandlers, ...serviceHandlers, ...parentHandlers, ...adminHandlers, ...studentHandlers]
let token = ''
async function call(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST', headers: Record<string, string> = {}) {
  const response = await getResponse(
    handlers,
    new Request('http://localhost/api/v1' + path, {
      method,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...headers },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    { baseUrl: 'http://localhost' },
  )
  assert.ok(response, path)
  const text = await response.text()
  return { status: response.status, data: text ? JSON.parse(text) : null }
}
async function parent() {
  setWorkspaceScenario('normal')
  const r = await call('/auth/login', { email: 'parent@example.test', password: 'demo-only' })
  assert.equal(r.status, 200)
  token = r.data.accessToken
  return (await call('/children')).data.items[0].childId as string
}
async function student(childId: string) {
  const r = await call('/auth/student-sessions', { childId })
  assert.equal(r.status, 201 in { 201: 1 } ? r.status : 200)
  token = r.data.accessToken
}
const weekday = (n: number | null) => {
  // Node에는 sessionStorage가 없어 요일 고정은 전역 대체로만 시험한다.
  const store = new Map<string, string>()
  if (n !== null) store.set(MOCK_WEEKDAY_KEY, String(n))
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v), removeItem: (k: string) => store.delete(k) },
  })
}
test.beforeEach(() => {
  weekday(null)
  resetRetention()
})

test('포인트 해금: 잔액 부족·판매 중단은 409, 같은 키는 한 번만 차감, 해금 뒤 꾸미기 저장', async () => {
  const childId = await parent()
  await student(childId)
  const before = (await call('/students/me/points')).data
  assert.equal(before.balance, balanceOf(childId))
  assert.ok(before.items.every((e: { amount: number }) => typeof e.amount === 'number'))

  const items = (await call('/students/me/look-items')).data.items as { itemKey: string; unlocked: boolean; pricePoints: number }[]
  assert.equal(items.find((i) => i.itemKey === 'THEME:lake')?.unlocked, true)
  assert.equal(items.find((i) => i.itemKey === 'THEME:space')?.unlocked, false)
  assert.equal(items.some((i) => i.itemKey === 'HAT_CROWN'), false, '판매 중단·미해금 아이템은 목록에 없음')

  assert.equal((await call('/students/me/look-items/THEME%3Aspace/unlock', undefined, 'POST')).status, 400, '키 없으면 거절')
  assert.equal((await call('/students/me/look-items/HAT_CROWN/unlock', undefined, 'POST', { 'Idempotency-Key': '00000000-0000-4000-8000-000000000001' })).data.code, 'LOOK_ITEM_NOT_ON_SALE')

  const first = await call('/students/me/look-items/THEME%3Aspace/unlock', undefined, 'POST', { 'Idempotency-Key': '00000000-0000-4000-8000-000000000002' })
  assert.equal(first.status, 200)
  const again = await call('/students/me/look-items/THEME%3Aspace/unlock', undefined, 'POST', { 'Idempotency-Key': '00000000-0000-4000-8000-000000000002' })
  assert.equal(again.data.balance, first.data.balance, '같은 키 재요청은 차감하지 않음')
  assert.equal(first.data.balance, before.balance - 100)

  const broke = await call('/students/me/look-items/COMPANION%3Atori/unlock', undefined, 'POST', { 'Idempotency-Key': '00000000-0000-4000-8000-000000000003' })
  assert.equal(broke.status, 409)
  assert.equal(broke.data.code, 'INSUFFICIENT_POINTS')

  assert.equal((await call('/students/me/preferences', { theme: 'space', companion: 'mungchi' }, 'PUT')).status, 200)
  const locked = await call('/students/me/preferences', { theme: 'space', companion: 'tori' }, 'PUT')
  assert.equal(locked.data.code, 'LOOK_LOCKED')
  const equip = await call('/students/me/preferences', { theme: 'space', companion: 'mungchi', equipped: { HAT: 'HAT_ACORN' } }, 'PUT')
  assert.equal(equip.data.code, 'LOOK_LOCKED', '해금하지 않은 아이템은 착용 불가')
})

const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const post = (path: string, key?: string) => call(path, undefined, 'POST', key ? { 'Idempotency-Key': key } : {})
type CatalogRow = { itemKey: string; slot: string; unlocked: boolean; onSale: boolean; ownedCount: number | null; createdAt: string | null }

test('#705 해금: 같은 키·다른 항목은 계약대로 422, 방 소품을 해금으로 부르면 422, 바닥은 해금·착용', async () => {
  const childId = await parent()
  await student(childId)
  const items = (await call('/students/me/look-items')).data.items as CatalogRow[]
  const floor = items.find((i) => i.itemKey === 'FLOOR_WOOD')!
  assert.deepEqual([floor.slot, floor.unlocked, floor.ownedCount], ['FLOOR', false, null])
  assert.ok(floor.createdAt && Number.isFinite(Date.parse(floor.createdAt)))
  assert.equal(items.find((i) => i.itemKey === 'THEME:space')?.createdAt, null, '테마·캐릭터 등록일은 null')
  assert.equal(items.find((i) => i.itemKey === 'HAT_ACORN')?.ownedCount, null)

  const decorUnlock = await post('/students/me/look-items/DECOR_PLANT/unlock', uuid(10))
  assert.deepEqual([decorUnlock.status, decorUnlock.data.code], [422, 'VALIDATION_FAILED'])

  const floorUnlock = await post('/students/me/look-items/FLOOR_WOOD/unlock', uuid(11))
  assert.equal(floorUnlock.status, 200)
  assert.equal(floorUnlock.data.balance, balanceOf(childId))
  const reused = await post('/students/me/look-items/HAT_ACORN/unlock', uuid(11))
  assert.deepEqual([reused.status, reused.data.code], [422, 'IDEMPOTENCY_KEY_REUSED'])
  // 거절(4xx)된 키도 그 항목에 묶여 다른 항목은 422(core도 처리 전에 요청을 기록)
  assert.equal((await post('/students/me/look-items/HAT_CROWN/unlock', uuid(12))).data.code, 'LOOK_ITEM_NOT_ON_SALE')
  assert.equal((await post('/students/me/look-items/HAT_ACORN/unlock', uuid(12))).status, 422)

  const equip = await call('/students/me/preferences', { theme: 'lake', companion: 'mungchi', equipped: { HAT: null, OUTFIT: null, ACCESSORY: null, BACKGROUND: null, FLOOR: 'FLOOR_WOOD' } }, 'PUT')
  assert.equal(equip.status, 200)
  assert.equal(equip.data.equipped.FLOOR, 'FLOOR_WOOD')
  assert.equal((await call('/students/me/preferences', { theme: 'lake', companion: 'mungchi', equipped: { FLOOR: 'FLOOR_MINT' } }, 'PUT')).data.code, 'LOOK_LOCKED')
  // 바닥을 보내지 않으면 착용 유지, null이면 벽지 세트의 바닥
  assert.equal((await call('/students/me/preferences', { theme: 'lake', companion: 'mungchi', equipped: { HAT: null } }, 'PUT')).data.equipped.FLOOR, 'FLOOR_WOOD')
  assert.equal((await call('/students/me/preferences', { theme: 'lake', companion: 'mungchi', equipped: { FLOOR: null } }, 'PUT')).data.equipped.FLOOR, null)
})

test('#705 방 소품 사기: 키마다 새 구매, 같은 키는 처음 응답, 8개 넘으면 409, 다른 칸·키 재사용은 422', async () => {
  const childId = await parent()
  await student(childId)
  const start = balanceOf(childId)
  const plant = async () => ((await call('/students/me/look-items')).data.items as CatalogRow[]).find((i) => i.itemKey === 'DECOR_PLANT')
  assert.deepEqual(await plant().then((p) => [p?.unlocked, p?.ownedCount]), [false, 0])

  assert.equal((await post('/students/me/look-items/DECOR_PLANT/purchase')).status, 400, '키 없으면 거절')
  const first = await post('/students/me/look-items/DECOR_PLANT/purchase', uuid(20))
  assert.deepEqual(first.data, { itemKey: 'DECOR_PLANT', ownedCount: 1, balance: start - 30 })
  const again = await post('/students/me/look-items/DECOR_PLANT/purchase', uuid(20))
  assert.deepEqual(again.data, first.data, '같은 키 재요청은 처음 응답, 한 번만 차감')
  const second = await post('/students/me/look-items/DECOR_PLANT/purchase', uuid(21))
  assert.deepEqual(second.data, { itemKey: 'DECOR_PLANT', ownedCount: 2, balance: start - 60 }, '키가 다르면 새 구매')
  assert.equal(balanceOf(childId), start - 60)
  assert.deepEqual(await plant().then((p) => [p?.unlocked, p?.ownedCount]), [true, 2])

  // 같은 키로 다른 항목·해금 경로에 쓴 키는 422
  assert.equal((await post('/students/me/look-items/DECOR_RUG/purchase', uuid(20))).data.code, 'IDEMPOTENCY_KEY_REUSED')
  assert.equal((await post('/students/me/look-items/FLOOR_WOOD/unlock', uuid(21))).data.code, 'IDEMPOTENCY_KEY_REUSED')
  // 방 소품이 아닌 항목은 422, 없는 항목은 404
  for (const itemKey of ['FLOOR_WOOD', 'HAT_ACORN', 'THEME%3Aspace']) {
    const r = await post(`/students/me/look-items/${itemKey}/purchase`, crypto.randomUUID())
    assert.deepEqual([r.status, r.data.code], [422, 'VALIDATION_FAILED'], itemKey)
  }
  assert.equal((await post('/students/me/look-items/NOPE/purchase', crypto.randomUUID())).data.code, 'LOOK_ITEM_NOT_FOUND')

  // 보유 상한 8개
  retentionState.decor[childId].DECOR_PLANT = 8
  const limit = await post('/students/me/look-items/DECOR_PLANT/purchase', uuid(22))
  assert.deepEqual([limit.status, limit.data.code], [409, 'LOOK_DECOR_LIMIT'])
  assert.equal(balanceOf(childId), start - 60, '상한이면 차감 없음')

  // 잔액 부족은 해금과 같은 코드
  retentionState.decor[childId].DECOR_PLANT = 2
  retentionState.ledger[childId].push({ eventType: 'UNLOCK', amount: -(start - 60) + 10, createdAt: '2026-11-17T00:00:00Z', sourceKey: 'drain' })
  const broke = await post('/students/me/look-items/DECOR_PLANT/purchase', uuid(23))
  assert.deepEqual([broke.status, broke.data.code], [409, 'INSUFFICIENT_POINTS'])

  // 판매 중단: 새로 살 수 없고 가진 것은 목록에 보유 개수와 남는다. 안 가진 판매 중단 방 소품은 목록에서 빠진다
  for (const i of retentionState.items) if (i.code === 'DECOR_PLANT' || i.code === 'DECOR_RUG') i.status = 'STOPPED'
  const stopped = await post('/students/me/look-items/DECOR_PLANT/purchase', uuid(24))
  assert.deepEqual([stopped.status, stopped.data.code], [409, 'LOOK_ITEM_NOT_ON_SALE'])
  assert.deepEqual(await plant().then((p) => [p?.onSale, p?.ownedCount]), [false, 2])
  assert.equal(((await call('/students/me/look-items')).data.items as CatalogRow[]).some((i) => i.itemKey === 'DECOR_RUG'), false)
})

test('#705 방 소품 놓은 칸(core #723 계약안 + color): 범위·같은 기준 칸·8개·보유·색 형식은 422, 면→row→col 정렬', async () => {
  const childId = await parent()
  await student(childId)
  const put = (spots: unknown) => call('/students/me/room/decor-spots', { spots }, 'PUT')
  assert.deepEqual((await call('/students/me/room/decor-spots')).data, { spots: [] })
  retentionState.decor[childId] = { DECOR_PLANT: 2, DECOR_LIGHTS: 1 }
  const ok = await put([
    { surface: 'WALL_BACK', col: 3, row: 2, itemKey: 'DECOR_LIGHTS', color: null },
    { surface: 'FLOOR', col: 12, row: 6, itemKey: 'DECOR_PLANT', color: 'sky' },
    { surface: 'FLOOR', col: 2, row: 6, itemKey: 'DECOR_PLANT' },
  ])
  assert.equal(ok.status, 200)
  assert.deepEqual(ok.data.spots.map((s: { surface: string; col: number; row: number; color: string | null }) => [s.surface, s.col, s.row, s.color]),
    [['FLOOR', 2, 6, null], ['FLOOR', 12, 6, 'sky'], ['WALL_BACK', 3, 2, null]], '면 → row → col, 색 없으면 null')
  assert.equal(ok.data.spots[0].assetKey, 'room/decor-plant.svg')
  assert.deepEqual((await call('/students/me/room/decor-spots')).data, ok.data, '다시 조회해도 같은 칸·같은 색')
  const bad = async (spots: unknown, why: string) => {
    const r = await put(spots)
    assert.deepEqual([r.status, r.data.code], [422, 'VALIDATION_FAILED'], why)
  }
  await bad([{ surface: 'FLOOR', col: 17, row: 0, itemKey: 'DECOR_PLANT' }], '바닥 칸 범위 밖')
  await bad([{ surface: 'WALL_LEFT', col: 11, row: 0, itemKey: 'DECOR_LIGHTS' }], '왼쪽 벽 칸 범위 밖')
  await bad([{ surface: 'FLOOR', col: 1, row: 1, itemKey: 'DECOR_PLANT' }, { surface: 'FLOOR', col: 1, row: 1, itemKey: 'DECOR_PLANT' }], '같은 기준 칸 두 번')
  await bad([1, 2, 3].map((col) => ({ surface: 'FLOOR', col, row: 9, itemKey: 'DECOR_PLANT' })), '보유 2개보다 많이')
  await bad([{ surface: 'FLOOR', col: 1, row: 1, itemKey: 'DECOR_RUG' }], '가지지 않은 방 소품')
  await bad([{ surface: 'FLOOR', col: 1, row: 1, itemKey: 'DECOR_PLANT', color: 'Sky Blue' }], '색 형식')
  retentionState.decor[childId].DECOR_PLANT = 8
  await bad(Array.from({ length: 9 }, (_, col) => ({ surface: 'FLOOR', col, row: 10, itemKey: 'DECOR_PLANT' })), '9개')
  assert.deepEqual((await call('/students/me/room/decor-spots')).data, ok.data, '거절되면 저장된 것이 바뀌지 않음')
  assert.deepEqual((await put([])).data, { spots: [] }, '빈 목록은 모두 치움')
})

test('커뮤니티: 보호자 COMMUNITY 동의 전에는 켤 수 없고, 철회하면 공개가 꺼진다', async () => {
  const childId = await parent()
  const docs = (await call('/consent-documents')).data.items as { kind: string; documentId: string; version: string }[]
  const community = docs.find((d) => d.kind === 'COMMUNITY')!
  assert.ok(community)

  await student(childId)
  assert.deepEqual(
    { enabled: (await call('/students/me/community-settings')).data.enabled, consent: (await call('/students/me/community-settings')).data.consentGranted },
    { enabled: false, consent: false },
  )
  assert.equal((await call('/students/me/community-settings', { enabled: true }, 'PUT')).data.code, 'COMMUNITY_CONSENT_REQUIRED')

  await parent()
  const agreed = await call('/me/consents', { childId, consents: [{ documentId: community.documentId, version: community.version, agreed: true }] })
  assert.equal(agreed.status, 200)
  const consentId = agreed.data.items[0].consentId as string

  await student(childId)
  assert.equal((await call('/students/me/community-settings', { enabled: true }, 'PUT')).data.enabled, true)

  await parent()
  assert.equal((await call(`/me/consents/${consentId}/withdrawal`, {})).status, 200)
  await student(childId)
  const after = (await call('/students/me/community-settings')).data
  assert.deepEqual({ enabled: after.enabled, consentGranted: after.consentGranted }, { enabled: false, consentGranted: false })
})

test('주간 테마(#484 규칙): 공개된 문제는 쌓여 열리고, 토요일 되돌아보기는 주 1회 적립', async () => {
  weekday(1) // 화요일
  const childId = await parent()
  await student(childId)
  const week = (await call('/students/me/weekly-theme')).data
  assert.deepEqual(week.days.map((d: { state: string }) => d.state), ['OPEN', 'OPEN', 'LOCKED', 'LOCKED', 'LOCKED'], '월요일 문제도 계속 열림')
  assert.ok(week.intro, '시작 이야기는 그 주 첫 진입 때 보이도록 매일 채움')
  assert.equal(week.introSeen, false)
  assert.equal(week.ending, 'NOT_ENDED')
  assert.equal(week.outro, null, '엔딩 전에는 종료 이야기·정답을 비움')
  assert.equal(week.answer, null)
  assert.equal(week.candidates.length, 4)
  assert.equal(week.review.open, false)

  const locked = week.days.find((d: { state: string; attemptStatus: string }) => d.state === 'LOCKED' && d.attemptStatus === 'NOT_STARTED')
  if (locked) assert.equal((await call(`/missions/${locked.missionId}/attempts`, { context: 'THEME_DAY' })).data.code, 'THEME_DAY_CLOSED')
  const monday = week.days[0]
  if (monday.attemptStatus === 'NOT_STARTED')
    assert.equal((await call(`/missions/${monday.missionId}/attempts`, { context: 'THEME_DAY' })).status, 201, '지난 요일 공개 문제도 새로 시작')
  assert.equal((await call('/students/me/weekly-theme/review-views', {})).data.code, 'THEME_REVIEW_NOT_ALLOWED')

  weekday(5) // 토요일
  const weekend = (await call('/students/me/weekly-theme')).data
  assert.equal(weekend.review.open, true)
  assert.ok(weekend.days.every((d: { state: string }) => d.state === 'OPEN'), '토요일엔 안 푼 문제도 새로 풀기')
  const before = balanceOf(childId)
  assert.equal((await call('/students/me/weekly-theme/review-views', {})).data.firstViewThisWeek, true)
  assert.equal((await call('/students/me/weekly-theme/review-views', {})).data.firstViewThisWeek, false)
  assert.equal(balanceOf(childId), before + 10, '되돌아보기 열람 적립은 주 1회')
})

test('주간 테마 일요일: 무료는 닫힘(풀기·되돌아보기·새 이야기 거부), 프리미엄은 토요일과 같음', async () => {
  weekday(6)
  await parent()
  // 이용권은 자녀 정보가 아니라 결제 목업 구독에서 정한다(#602)
  const children = (await call('/children')).data.items as { childId: string }[]
  const freeChild = children.find((c) => !mockPremium(c.childId))!
  const premiumChild = children.find((c) => mockPremium(c.childId))!
  await student(freeChild.childId)
  const free = (await call('/students/me/weekly-theme')).data
  assert.ok(free.days.every((d: { state: string }) => d.state === 'CLOSED'))
  assert.equal(free.review.open, false)
  assert.equal((await call('/students/me/weekly-theme/review-views', {})).data.code, 'THEME_REVIEW_NOT_ALLOWED')
  assert.equal((await call('/students/me/weekly-theme/story-views', { kind: 'INTRO' })).data.code, 'THEME_STORY_NOT_ALLOWED')

  await parent()
  await student(premiumChild.childId)
  const premium = (await call('/students/me/weekly-theme')).data
  assert.ok(premium.days.every((d: { state: string }) => d.state === 'OPEN'))
  assert.equal(premium.review.open, true)
  assert.equal((await call('/students/me/weekly-theme/story-views', { kind: 'INTRO' })).status, 200)
})

test('이야기 열람: INTRO는 주 1회 기록, OUTRO는 엔딩 전 409, 형식 밖 400', async () => {
  weekday(2)
  const childId = await parent()
  await student(childId)
  assert.equal((await call('/students/me/weekly-theme/story-views', { kind: 'INTRO' })).data.firstViewThisWeek, true)
  assert.equal((await call('/students/me/weekly-theme/story-views', { kind: 'INTRO' })).data.firstViewThisWeek, false)
  assert.equal((await call('/students/me/weekly-theme')).data.introSeen, true)
  assert.equal((await call('/students/me/weekly-theme/story-views', { kind: 'OUTRO' })).data.code, 'THEME_STORY_NOT_ALLOWED')
  assert.equal((await call('/students/me/weekly-theme/story-views', { kind: 'MIDDLE' })).status, 400)
})

test('정답 고르기: 후보 밖 400, 금요일 문제 학습 완료 전 409. 맞히면 바로 엔딩, 틀리면 토요일 금요일 다시 풀기 뒤 엔딩', async () => {
  weekday(4)
  const childId = await parent()
  await student(childId)
  assert.equal((await call('/students/me/weekly-theme/answer-picks', { pick: '아무개' })).status, 400)
  const fridayOpen = (await call('/students/me/weekly-theme')).data.days[4]
  if (fridayOpen.attemptStatus !== 'COMPLETED')
    assert.equal((await call('/students/me/weekly-theme/answer-picks', { pick: MOCK_STORY.candidates[0] })).data.code, 'THEME_PICK_NOT_ALLOWED')

  // 엔딩 판정은 목업 함수에 금요일 문제 학습 완료 상태를 넣어 확인한다.
  const done = [...THINKING_ORDER].map((t, i) => ({ id: `m${i}`, title: t, thinkingType: t, status: 'COMPLETED' })) as unknown as Mission[]
  const week = `s1:${weekStart()}`
  retentionState.picks[week] = { pick: MOCK_STORY.answer, correct: true, at: '2026-11-13T01:00:00Z' }
  const right = weeklyThemeFor('s1', done, 4)
  assert.deepEqual([right.ending, right.answer, right.outro], ['ENDED', MOCK_STORY.answer, MOCK_STORY.outro])
  assert.ok(right.days.every((d) => d.clue), '마무리한 문제의 단서가 열림')

  assert.deepEqual(right.answerPick, { pick: MOCK_STORY.answer, correct: true }, '#590 고른 정답을 조회에 담음')
  retentionState.picks[week] = { pick: MOCK_STORY.candidates[0], correct: false, at: '2026-11-13T01:00:00Z' }
  const wrong = weeklyThemeFor('s1', done, 4)
  assert.deepEqual([wrong.ending, wrong.answer, wrong.answerPick], ['NOT_ENDED', null, { pick: MOCK_STORY.candidates[0], correct: false }], '틀리면 바로 엔딩 아님, 정답은 숨김')
  weekday(5)
  retentionState.completions[`s1:${weekStart()}:m4`] = { weekday: 5, at: '2026-11-14T01:00:00Z' }
  const after = weeklyThemeFor('s1', done, 4)
  assert.deepEqual([after.ending, after.answer], ['ENDED', MOCK_STORY.answer], '토요일 금요일 문제 다시 풀기 마무리 뒤 엔딩·정답 공개')
})

test('학부모 리포트: 일일·주간 구분, 일일 리포트로만 고정 대화를 만든다', async () => {
  const childId = await parent()
  const daily = (await call(`/children/${childId}/reports?periodType=DAILY`)).data.items as { reportId: string; periodType: string; period: { from: string; to: string } }[]
  const weekly = (await call(`/children/${childId}/reports?periodType=WEEKLY`)).data.items as { reportId: string; periodType: string }[]
  assert.ok(daily.length && daily.every((r) => r.periodType === 'DAILY' && r.period.from === r.period.to))
  assert.ok(weekly.length && weekly.every((r) => r.periodType === 'WEEKLY'))
  assert.equal((await call(`/children/${childId}/reports`)).data.items.length, daily.length + weekly.length)

  const detail = (await call(`/reports/${daily[0].reportId}`)).data
  assert.ok(Array.isArray(detail.problems))
  assert.ok(detail.problems.every((p: { answerTimes?: unknown }) => Array.isArray(p.answerTimes)), '#803 문제별 answerTimes(없으면 [])')
  assert.equal(detail.narrative, null, '일일 리포트는 서술 없음')
  assert.ok(!detail.eveningQuestion, '저녁 질문은 주간에만')
  if (detail.parentSharingEnabled === false)
    assert.ok(detail.problems.every((p: { finalAnswer: unknown; quotes: unknown[] }) => p.finalAnswer === null && !p.quotes.length), '원문 비공개면 문제별 원문도 숨김')

  saveSharing(childId, true) // 대화는 학생이 원문을 공개했을 때만
  const badWeekly = await call('/conversations', { childId, reportId: weekly[0].reportId })
  assert.ok([422, 429].includes(badWeekly.status), '주간 리포트 ID는 고정 대화 불가(무료면 먼저 429)')
  if (badWeekly.status === 422) {
    assert.equal(badWeekly.data.code, 'CONVERSATION_REPORT_INVALID')
    const fixed = await call('/conversations', { childId, reportId: daily[0].reportId })
    assert.equal(fixed.data.reportId, daily[0].reportId)
    assert.deepEqual(fixed.data.period, daily[0].period)
  }
  assert.equal((await call(`/children/${childId}/points`)).status, 200)
  assert.ok(Array.isArray((await call(`/children/${childId}/community-posts`)).data.items))
})

test('#481 목업: 저장된 주간 리포트도 설명 미포함·무료 전환·비공개를 현재 조건으로 적용한다', async () => {
  const childId = await parent()
  assert.equal(setMockChildPlan({ childId, plan: 'PREMIUM' }), true)
  saveSharing(childId, true)
  const id = (await call(`/children/${childId}/reports?periodType=WEEKLY`)).data.items[0].reportId
  setWorkspaceScenario('explanation-missing')
  assert.deepEqual((await call(`/reports/${id}`)).data.explanations, { state: 'NOT_INCLUDED', items: [] })
  setWorkspaceScenario('normal')
  assert.notEqual((await call(`/reports/${id}`)).data.explanations?.state, 'NOT_INCLUDED')
  assert.equal(setMockChildPlan({ childId, plan: 'FREE' }), true)
  assert.equal((await call(`/reports/${id}`)).data.explanations, null)
  assert.equal(setMockChildPlan({ childId, plan: 'PREMIUM' }), true)
  saveSharing(childId, false)
  assert.deepEqual((await call(`/reports/${id}`)).data.explanations, { state: 'NO_TARGET', items: [] })
})

test('관리자: 주간 테마 작성→검토→게시 검사, 꾸미기 아이템은 삭제 없이 판매 중단', async () => {
  setWorkspaceScenario('normal')
  token = (await call('/auth/login', { email: 'content@example.test', password: 'demo-only' })).data.accessToken
  const created = await call('/admin/weekly-themes', {
    grade: 'G3',
    weekStart: '2026-11-16',
    title: '시험 테마',
    intro: '도입 이야기',
    days: [{ day: 'MON', missionId: '' }],
  })
  assert.equal(created.status, 201)
  const id = created.data.themeId as string
  assert.equal((await call(`/admin/weekly-themes/${id}/publish`, {})).status, 409, '검토 요청 전 게시 불가')
  assert.equal((await call(`/admin/weekly-themes/${id}/review-request`, {})).data.status, 'REVIEW_REQUIRED')
  const publish = await call(`/admin/weekly-themes/${id}/publish`, {})
  assert.equal(publish.status, 422)
  assert.equal(publish.data.code, 'WEEKLY_THEME_PUBLISH_INCOMPLETE')
  assert.ok(publish.data.errors.length > 0)
  assert.ok(publish.data.errors.some((e: { code: string }) => e.code === 'DAYS_INCOMPLETE'), '서버처럼 errors[{code, message}]')
  for (const e of publish.data.errors) assert.deepEqual(Object.keys(e).sort(), ['code', 'message'])
  assert.equal((await call('/admin/weekly-themes', { ...created.data, weekStart: '2026-11-17' })).status, 422, '월요일만')

  const item = await call('/admin/look-items', { code: 'HAT_TEST', slot: 'HAT', name: '시험 모자', pricePoints: 20, assetKey: 'looks/test.svg' })
  assert.equal(item.status, 201)
  assert.equal((await call('/admin/look-items', { code: 'HAT_TEST', slot: 'HAT', name: '중복', pricePoints: 20 })).status, 409)
  const stopped = await call(`/admin/look-items/${item.data.itemId}`, { status: 'STOPPED' }, 'PATCH')
  assert.equal(stopped.data.status, 'STOPPED')
  assert.ok((await call('/admin/look-items')).data.items.some((i: { code: string }) => i.code === 'HAT_TEST'), '삭제하지 않고 남는다')
})

test('관리자 바닥·방 소품 생성과 칸 필터는 기존 착용 칸과 구분한다 (#706)', async () => {
  token = (await call('/auth/login', { email: 'content@example.test', password: 'demo-only' })).data.accessToken
  for (const slot of ['FLOOR', 'DECOR']) {
    const created = await call('/admin/look-items', { code: `${slot}_TEST`, slot, name: '합성 시험 항목', pricePoints: 30, assetKey: `room/test-${slot.toLowerCase()}.svg` })
    assert.equal(created.status, 201)
    assert.equal(created.data.slot, slot)
    const filtered = await call(`/admin/look-items?slot=${slot}`)
    assert.ok(filtered.data.items.some((i: { code: string }) => i.code === `${slot}_TEST`))
    assert.ok(filtered.data.items.every((i: { slot: string }) => i.slot === slot))
  }
  assert.equal((await call('/admin/look-items?slot=UNKNOWN')).status, 422)
  assert.equal((await call('/admin/look-items', { code: 'UNKNOWN_TEST', slot: 'UNKNOWN', name: '잘못된 칸', pricePoints: 30, assetKey: 'test.svg' })).status, 422)
  const all = (await call('/admin/look-items')).data.items as { slot: string }[]
  assert.ok(['HAT', 'FLOOR', 'DECOR'].every(slot => all.some(i => i.slot === slot)))
  assert.ok((await call('/admin/look-items?slot=HAT')).data.items.every((i: { slot: string }) => i.slot === 'HAT'))
  const first = (await call('/admin/look-items?size=2')).data
  const next = (await call('/admin/look-items?size=2&page=1')).data
  assert.equal(first.items.length, 2)
  assert.equal(next.page, 1)
  assert.equal(first.totalElements, next.totalElements)
  assert.ok(first.items.every((item: { itemId: string }) => !next.items.some((other: { itemId: string }) => other.itemId === item.itemId)))
  assert.equal((await call('/admin/look-items?size=0')).status, 400)
})

test('관리자 테마 목업: 학년 네 개를 각각 저장·조회하며 숫자와 옛 학년군은 받지 않는다', async () => {
  token = (await call('/auth/login', { email: 'content@example.test', password: 'demo-only' })).data.accessToken
  const body = { weekStart: '2026-11-16', title: '학년별 검증 테마', intro: '도입 이야기', days: [] }
  for (const grade of ['G3', 'G4', 'G5', 'G6']) {
    const created = await call('/admin/weekly-themes', { ...body, grade })
    assert.equal(created.status, 201)
    assert.equal(created.data.grade, grade)
    assert.equal(Object.hasOwn(created.data, 'gradeBand'), false)
  }
  for (const grade of ['G3', 'G4', 'G5', 'G6']) {
    const filtered = await call(`/admin/weekly-themes?grade=${grade}`)
    assert.equal(filtered.status, 200)
    assert.deepEqual(filtered.data.items.map((t: { grade: string }) => t.grade), [grade])
  }
  for (const grade of ['G3_4', 'G5_6', 'G7', 3]) assert.equal((await call('/admin/weekly-themes', { ...body, grade })).status, 422)
  assert.equal((await call('/admin/weekly-themes', { ...body, gradeBand: 'G3_4' })).status, 422)
})

test('테마 목업: 같은 주의 게시 테마가 여러 개여도 학생 학년의 테마만 고른다', () => {
  const missions: Mission[] = THINKING_ORDER.map((thinkingType, i) => ({ id: `grade-mission-${i}`, title: '학년별 검증 미션', subject: '국어', grade: 3, gradeMax: 6,
    thinkingType, inputType: 'NARRATIVE', question: '어떻게 생각하나요?', hint: '까닭을 생각해 보세요.', scene: 'korean' }))
  for (const grade of ['G3', 'G4', 'G5', 'G6'] as const) retentionState.themes.push({ themeId: `theme-${grade}`, grade, weekStart: weekStart(), title: `${grade} 테마`, intro: '도입',
    status: 'PUBLISHED', updatedAt: '2026-11-10T00:00:00Z', days: THEME_DAYS.map((day, i) => ({ day, missionId: missions[i].id })) })
  for (const grade of [3, 4, 5, 6, 7, 8, 9]) assert.equal(themeMissions(missions, grade).themeId, `theme-G${Math.min(grade, 6)}`)
})

function prepareThemeMissions(t: import('node:test').TestContext, prefix: string) {
  weekday(0)
  // 편성 목업이 사용하는 브라우저 저장소도 이 시험의 메모리 저장소로 격리한다.
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: globalThis.sessionStorage })
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, 'localStorage', previous)
    else Reflect.deleteProperty(globalThis, 'localStorage')
  })
  const count = adminMissions.length
  const days = THEME_DAYS.map((day, i) => {
    const m = structuredClone(adminMissions[0]), id = prefix+i, thinkingType = THINKING_ORDER[i]
    m.missionId=id; m.status='PUBLISHED'; m.publishedVersion=m.currentVersion
    m.versions[0].thinkingType=thinkingType
    adminMissions.push(m)
    fixtureStore.publishCatalog(id, { id, title: day+' 게시본', subject: '국어', grade: 3, thinkingType,
      inputType:'NARRATIVE',question:day+' 게시한 질문',hint:'찾아보세요.',scene:'korean' })
    return { day, missionId:id }
  })
  t.after(() => {
    adminMissions.splice(count)
    days.forEach(d => fixtureStore.publishCatalog(d.missionId, null))
  })
  return days
}

async function contentAdmin() {
  token = (await call('/auth/login', { email: 'content@example.test', password: 'demo-only' })).data.accessToken
}

test('주간 게시 후 일반 미션 수정·공개 중단에도 주간 안내와 시도는 게시 질문을 사용한다', async (t) => {
    const days = prepareThemeMissions(t, 'weekly-pinned-882-')
    const childId = await parent()
    await contentAdmin()
    const created = await call('/admin/weekly-themes', {grade:'G3',weekStart:weekStart(),title:'버전 고정',intro:'도입',days})
    assert.equal(created.status,201)
    const detail = '/admin/weekly-themes/'+created.data.themeId
    assert.equal((await call(detail+'/review-request',{})).status,200)
    const publication = await call(detail+'/publish',{})
    assert.equal(publication.status,200,JSON.stringify(publication.data))
    const id = days[0].missionId, base = '/missions/'+id
    const original = fixtureStore.snapshot().catalog!.find(m=>m.id===id)!
    fixtureStore.publishCatalog(id,{...original,question:'최신 질문'})
    await parent(); await student(childId)
    assert.equal((await call(base)).data.question,'최신 질문')
    assert.equal((await call(base+'?context=THEME_DAY')).data.question,original.question)
    fixtureStore.publishCatalog(id,null)
    assert.equal((await call(base)).status,404)
    assert.equal((await call('/students/me/weekly-theme')).data.days[0].missionId,id)
    assert.equal((await call(base+'?context=THEME_DAY')).data.question,original.question)
    assert.equal((await call(base+'?context=THEME_REVIEW')).data.code,'THEME_REVIEW_NOT_ALLOWED')
    assert.equal((await call(base+'/attempts',{context:'THEME_DAY'})).data.mission.question,original.question)
    assert.equal((await call('/students/me/weekly-theme')).data.days[0].attemptStatus,'IN_PROGRESS')
})

test('게시본 수정·재검토·재게시·제공 중단 과정에서 학생과 편성표는 실제 게시 버전을 따른다', async (t) => {
  const days = prepareThemeMissions(t, 'weekly-republish-')
  const childId = await parent()
  await contentAdmin()
  const source = { grade: 'G3', weekStart: weekStart(), title: '처음 게시', intro: '이전 도입', days }
  const created = await call('/admin/weekly-themes', source)
  const detail = '/admin/weekly-themes/' + created.data.themeId
  const other = await call('/admin/weekly-themes', { ...source, title: '다른 후보' })
  const otherDetail = '/admin/weekly-themes/' + other.data.themeId
  assert.equal((await call(otherDetail + '/review-request', {})).status, 200)
  assert.equal((await call(detail + '/review-request', undefined, 'POST')).status, 200)
  assert.equal((await call(detail + '/publish', {})).data.publishedVersion, 1)
  assert.equal((await call(otherDetail + '/publish', {})).data.code, 'WEEK_LOCKED')

  const revision = { ...source, title: '수정한 테마', intro: '수정한 도입', expectedVersion: 1 }
  const save = await call(detail, revision, 'PUT')
  assert.deepEqual([save.data.status, save.data.version, save.data.publishedVersion, save.data.reviewRequested], ['PUBLISHED', 2, 1, false])
  assert.equal((await call(detail, revision, 'PUT')).data.code, 'PLAN_CONFLICT')
  assert.equal((await call(detail + '/publish', { expectedVersion: 2 })).status, 409)
  assert.equal((await call(detail + '/review-request', { expectedVersion: 1 })).data.code, 'PLAN_CONFLICT')
  assert.equal((await call(detail + '/review-request', { expectedVersion: 2 })).data.reviewRequested, true)

  // 편집과 검토 요청 뒤 새 탭에서 복원해도 게시 제목·도입과 요일별 미션은 유지된다.
  retentionState.themes = JSON.parse(sessionStorage.getItem('sagomungchi:msw-retention:v1')!).themes
  const board = await call('/admin/weekly-themes/planner?grade=G3&weekStart=' + weekStart())
  const live = board.data.weeks[0].themes.find((row: { status: string }) => row.status === 'PUBLISHED')
  assert.deepEqual([board.data.weeks[0].locked, live.title, live.version], [true, source.title, 1])
  assert.equal((await call(detail)).data.title, revision.title)
  const monday = days[0].missionId
  const catalog = fixtureStore.snapshot().catalog!.find(m => m.id === monday)!
  fixtureStore.publishCatalog(monday, { ...catalog, question: '재게시한 질문' })
  await parent()
  await student(childId)
  const before = (await call('/students/me/weekly-theme')).data
  assert.deepEqual([before.title, before.intro], [source.title, source.intro])
  const attemptPath = '/missions/' + monday + '/attempts'
  const started = (await call(attemptPath, { context: 'THEME_DAY' })).data
  assert.equal(started.mission.question, catalog.question)

  await contentAdmin()
  assert.equal((await call(detail + '/publish', { expectedVersion: 2, expectedPlannedDraftId: null })).data.publishedVersion, 2)
  const after = themeMissions([], 3)
  assert.deepEqual([after.title, after.intro, after.days[0].mission.question], [revision.title, revision.intro, '재게시한 질문'])
  assert.equal((await call(detail + '/unpublish', { expectedPublishedVersion: 1 })).data.code, 'PLAN_CONFLICT')
  const stopped = (await call(detail + '/unpublish', { expectedPublishedVersion: 2 })).data
  assert.deepEqual([stopped.status, stopped.publishedVersion, stopped.reviewRequested], ['UNPUBLISHED', 2, false])
  assert.equal((await call(detail + '/publish', {})).status, 409)
  await parent()
  await student(childId)
  assert.equal((await call('/students/me/weekly-theme')).status, 404)
  assert.equal((await call('/students/me/weekly-theme/story-views', { kind: 'INTRO' })).status, 404)
  assert.equal((await call('/missions/' + monday + '?context=THEME_DAY')).data.question, catalog.question)
  assert.equal((await call('/missions/' + monday + '?context=THEME_REVIEW')).data.code, 'THEME_REVIEW_NOT_ALLOWED')
  assert.equal((await call('/missions/' + days[1].missionId + '?context=THEME_DAY')).data.code, 'THEME_DAY_CLOSED')
  assert.equal((await call('/missions/' + days[1].missionId + '/attempts', { context: 'THEME_DAY' })).status, 409)
  const resumed = (await call(attemptPath, { context: 'THEME_DAY' })).data
  assert.deepEqual([resumed.attemptId, resumed.mission.question], [started.attemptId, catalog.question])

  fixtureStore.publishCatalog(monday, { ...catalog, question: '개별 미션에서만 수정한 질문' })
  await contentAdmin()
  assert.equal((await call(detail + '/review-request', { expectedVersion: 2 })).data.status, 'REVIEW_REQUIRED')
  assert.equal((await call(detail + '/publish', { expectedVersion: 2 })).data.publishedVersion, 2)
  assert.equal(themeMissions([], 3).days[0].mission.question, '재게시한 질문')
})
