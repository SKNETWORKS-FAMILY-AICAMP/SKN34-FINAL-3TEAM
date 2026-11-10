import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { retentionHandlers } from '../src/mocks/handlers/retention.ts'
import { serviceHandlers } from '../src/mocks/handlers/service.ts'
import { parentHandlers } from '../src/mocks/handlers/parent.ts'
import { adminHandlers } from '../src/mocks/handlers/admin.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { balanceOf, MOCK_WEEKDAY_KEY, resetRetention, retentionState, themeMissions, weekStart } from '../src/mocks/fixtures/retention.ts'
import type { Mission } from '../src/domain/classroom.ts'
import { THEME_DAYS } from '../src/domain/retention.ts'
import { THINKING_ORDER } from '../src/domain/studentLook.ts'
import { saveSharing } from '../src/mocks/fixtures/sharing.ts'

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

test('주간 테마: 요일 상태·당일 문제만 시작, 주말 되돌아보기는 주 1회 적립', async () => {
  weekday(1) // 화요일
  const childId = await parent()
  await student(childId)
  const week = (await call('/students/me/weekly-theme')).data
  assert.deepEqual(week.days.map((d: { state: string }) => d.state), ['CLOSED', 'OPEN', 'LOCKED', 'LOCKED', 'LOCKED'])
  assert.equal(week.intro, null, '도입 이야기는 월요일에만')
  assert.equal(week.review.open, false)

  const closed = week.days.find((d: { state: string; attemptStatus: string }) => d.state === 'LOCKED' && d.attemptStatus === 'NOT_STARTED')
  if (closed) assert.equal((await call(`/missions/${closed.missionId}/attempts`, { context: 'THEME_DAY' })).data.code, 'THEME_DAY_CLOSED')
  assert.equal((await call('/students/me/weekly-theme/review-views', {})).data.code, 'THEME_REVIEW_NOT_ALLOWED')

  weekday(5) // 토요일
  const weekend = (await call('/students/me/weekly-theme')).data
  assert.equal(weekend.review.open, true)
  const before = balanceOf(childId)
  assert.equal((await call('/students/me/weekly-theme/review-views', {})).data.firstViewThisWeek, true)
  assert.equal((await call('/students/me/weekly-theme/review-views', {})).data.firstViewThisWeek, false)
  assert.equal(balanceOf(childId), before + 10, '되돌아보기 열람 적립은 주 1회')
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
  assert.equal((await call('/admin/weekly-themes', { ...created.data, weekStart: '2026-11-17' })).status, 422, '월요일만')

  const item = await call('/admin/look-items', { code: 'HAT_TEST', slot: 'HAT', name: '시험 모자', pricePoints: 20, assetKey: 'looks/test.svg' })
  assert.equal(item.status, 201)
  assert.equal((await call('/admin/look-items', { code: 'HAT_TEST', slot: 'HAT', name: '중복', pricePoints: 20 })).status, 409)
  const stopped = await call(`/admin/look-items/${item.data.itemId}`, { status: 'STOPPED' }, 'PATCH')
  assert.equal(stopped.data.status, 'STOPPED')
  assert.ok((await call('/admin/look-items')).data.items.some((i: { code: string }) => i.code === 'HAT_TEST'), '삭제하지 않고 남는다')
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
