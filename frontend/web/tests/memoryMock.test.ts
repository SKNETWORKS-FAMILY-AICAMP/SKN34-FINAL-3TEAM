import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { memoryHandlers, MOCK_MEMORY_SCENARIO_KEY, resetMemoryUsage } from '../src/mocks/handlers/memory.ts'
import { retentionHandlers } from '../src/mocks/handlers/retention.ts'
import { serviceHandlers } from '../src/mocks/handlers/service.ts'
import { parentHandlers } from '../src/mocks/handlers/parent.ts'
import { adminHandlers } from '../src/mocks/handlers/admin.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { MOCK_ALBUM_EMPTY_KEY, resetRetention } from '../src/mocks/fixtures/retention.ts'
import { explanationAttempts, readMemoryExplanation, readMemorySearch } from '../src/domain/memory.ts'

// 추억 검색·설명 목업 계약(API 명세 2.12, #567): 이슈 지침의 결과·결과 없음·기록 없음·한도·장애·설명 3상태.
const handlers = [...memoryHandlers, ...retentionHandlers, ...serviceHandlers, ...parentHandlers, ...adminHandlers, ...studentHandlers]
let token = ''
async function call(path: string, body?: unknown) {
  const response = await getResponse(
    handlers,
    new Request('http://localhost/api/v1' + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    { baseUrl: 'http://localhost' },
  )
  assert.ok(response, path)
  const text = await response.text()
  return { status: response.status, data: text ? JSON.parse(text) : null }
}
const storage = new Map<string, string>()
async function studentSession() {
  setWorkspaceScenario('normal')
  token = (await call('/auth/login', { email: 'parent@example.test', password: 'demo-only' })).data.accessToken
  const childId = (await call('/children')).data.items[0].childId as string
  token = (await call('/auth/student-sessions', { childId })).data.accessToken
}
test.beforeEach(async () => {
  storage.clear()
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: { getItem: (k: string) => storage.get(k) ?? null, setItem: (k: string, v: string) => storage.set(k, v), removeItem: (k: string) => storage.delete(k) },
  })
  resetRetention()
  resetMemoryUsage()
  await studentSession()
})

test('검색 결과 카드는 앨범 회차와 같아 회차 상세로 열리고, 관련 없는 질문은 결과 없음', async () => {
  const album = (await call('/students/me/album')).data
  const title = album.items[0].title as string
  const r = await call('/students/me/memories/search', { query: title })
  assert.equal(r.status, 200)
  const search = readMemorySearch(r.data)
  assert.equal(search.state, 'RESULTS')
  assert.ok(search.cards.length >= 1 && search.cards.length <= 3)
  const first = search.cards[0]
  assert.equal(first.title, title)
  assert.equal((await call(`/students/me/album/${first.themeId}/${first.weekStart}`)).status, 200)
  assert.deepEqual(readMemorySearch((await call('/students/me/memories/search', { query: '우주선 발사대' })).data), { state: 'NO_RESULTS', cards: [] })
})

test('보유 액자가 없으면 기록 없음, 형식 오류는 400', async () => {
  storage.set(MOCK_ALBUM_EMPTY_KEY, '1')
  assert.equal((await call('/students/me/memories/search', { query: '아무거나' })).data.state, 'NO_RECORDS')
  assert.equal((await call('/students/me/memories/search', { query: '   ' })).status, 400)
  assert.equal((await call('/students/me/memories/search', { query: '가'.repeat(201) })).status, 400)
})

test('검색 하루 한도: 20회 뒤 429, 장애 503은 횟수를 쓰지 않는다', async () => {
  storage.set(MOCK_MEMORY_SCENARIO_KEY, 'SEARCH_DOWN')
  const down = await call('/students/me/memories/search', { query: '지도' })
  assert.equal(down.status, 503)
  assert.equal(down.data.code, 'AI_UNAVAILABLE')
  storage.delete(MOCK_MEMORY_SCENARIO_KEY)
  for (let i = 0; i < 20; i++) assert.equal((await call('/students/me/memories/search', { query: '지도' })).status, 200, `검색 ${i + 1}회`)
  const limited = await call('/students/me/memories/search', { query: '지도' })
  assert.equal(limited.status, 429)
  assert.equal(limited.data.code, 'USAGE_LIMIT_REACHED')
  assert.match(limited.data.detail, /내일 0시\(KST\)/)
})

test('설명: GENERATED는 문장마다 근거 번호, INSUFFICIENT·FAILED는 글 없음, 503은 횟수 안 씀, 남의 기록은 422, 10회 뒤 429', async () => {
  const album = (await call('/students/me/album')).data
  const search = readMemorySearch((await call('/students/me/memories/search', { query: album.items[0].title })).data)
  const attemptIds = explanationAttempts(search.cards)
  const ok = await call('/students/me/memories/explanations', { query: '그때 뭐 했지', attemptIds })
  assert.equal(ok.status, 200)
  const e = readMemoryExplanation(ok.data, attemptIds)
  assert.equal(e.state, 'GENERATED')
  assert.match(e.text!, /\[1\]\./)
  for (const [key, state] of [['EXPLAIN_FAILED', 'FAILED'], ['EXPLAIN_INSUFFICIENT', 'INSUFFICIENT']] as const) {
    storage.set(MOCK_MEMORY_SCENARIO_KEY, key)
    assert.deepEqual(readMemoryExplanation((await call('/students/me/memories/explanations', { query: '질문', attemptIds })).data, attemptIds),
      { state, text: null, citations: [] })
  }
  storage.set(MOCK_MEMORY_SCENARIO_KEY, 'EXPLAIN_DOWN')
  for (let i = 0; i < 12; i++) assert.equal((await call('/students/me/memories/explanations', { query: '질문', attemptIds })).status, 503)
  storage.delete(MOCK_MEMORY_SCENARIO_KEY)
  assert.equal((await call('/students/me/memories/explanations', { query: '질문', attemptIds: ['someone-else'] })).status, 422)
  assert.equal((await call('/students/me/memories/explanations', { query: '질문', attemptIds: [] })).status, 400)
  // 지금까지 센 설명: GENERATED·FAILED·INSUFFICIENT·422 = 4회 → 6회 더 쓰면 11번째에 429
  for (let i = 0; i < 6; i++) assert.equal((await call('/students/me/memories/explanations', { query: '질문', attemptIds })).status, 200)
  assert.equal((await call('/students/me/memories/explanations', { query: '질문', attemptIds })).status, 429)
})
