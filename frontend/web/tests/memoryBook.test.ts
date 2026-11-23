import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { memoryBookHandlers, MOCK_MEMORY_BOOK_SCENARIO_KEY, resetMockMemoryBooks } from '../src/mocks/handlers/memoryBook.ts'
import { retentionHandlers } from '../src/mocks/handlers/retention.ts'
import { serviceHandlers } from '../src/mocks/handlers/service.ts'
import { parentHandlers } from '../src/mocks/handlers/parent.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { resetRetention } from '../src/mocks/fixtures/retention.ts'
import { saveSharing } from '../src/mocks/fixtures/sharing.ts'
import { setMockSubscription } from '../src/mocks/fixtures/payments.ts'
import { ApiError } from '../src/data/apiClient.ts'
import {
  bookOfRound,
  memoryBookFailure,
  memoryBookPolling,
  readMemoryBook,
  readMemoryBookDownload,
  readMemoryBookPage,
} from '../src/domain/memoryBook.ts'

// 추억 그림책 (docs/proposals/memory-book.md, 미도입 시험 구현): 응답 읽기·오류 문구와 목업 계약. 가상 값만 쓴다.

const book = (over: Record<string, unknown> = {}) => ({
  bookId: 'b1', status: 'READY', failureCode: null, rounds: [{ themeId: 't1', weekStart: '2026-11-02' }],
  createdAt: '2026-11-23T00:00:00Z', completedAt: '2026-11-23T00:00:05Z', expiresAt: '2026-12-23T00:00:00Z', ...over,
})

test('그림책 응답은 상태·회차·시각을 검사하고 모르는 값은 성공으로 바꾸지 않는다', () => {
  assert.equal(readMemoryBook(book()).status, 'READY')
  assert.equal(readMemoryBook(book({ status: 'EXPIRED' })).status, 'EXPIRED')
  assert.equal(readMemoryBook(book({ status: 'FAILED', failureCode: 'RENDER_FAILED', completedAt: null })).failureCode, 'RENDER_FAILED')
  for (const bad of [null, book({ status: 'DONE' }), book({ rounds: [] }), book({ rounds: [{ themeId: 't1', weekStart: '11/02' }] }),
    book({ createdAt: 'yesterday' }), book({ bookId: '' })])
    assert.throws(() => readMemoryBook(bad), /확인하지 못/)
  assert.equal(readMemoryBookPage({ items: [book()], page: 0, size: 50, totalElements: 1 }).items.length, 1)
  assert.throws(() => readMemoryBookPage({ items: 'x', page: 0, size: 50, totalElements: 0 }), /확인하지 못/)
})

test('받기 주소는 http(s)이고 만료 전일 때만 쓴다', () => {
  const now = Date.parse('2026-11-23T00:00:00Z')
  assert.equal(readMemoryBookDownload({ url: 'https://files.test/b.pdf', expiresAt: '2026-11-23T00:05:00Z' }, now).url, 'https://files.test/b.pdf')
  assert.equal(readMemoryBookDownload({ url: '/demo/memory-book-sample.pdf', expiresAt: '2026-11-23T00:05:00Z' }, now).url, '/demo/memory-book-sample.pdf')
  assert.throws(() => readMemoryBookDownload({ url: 'javascript:alert(1)', expiresAt: '2026-11-23T00:05:00Z' }, now), /확인하지 못/)
  assert.throws(() => readMemoryBookDownload({ url: 'https://files.test/b.pdf', expiresAt: '2026-11-22T23:59:00Z' }, now), /만료/)
})

test('회차의 최근 그림책·만드는 중 다시 보기·오류 문구', () => {
  const items = [readMemoryBook(book({ bookId: 'new', status: 'QUEUED' })), readMemoryBook(book({ bookId: 'old' }))]
  assert.equal(bookOfRound(items, 't1', '2026-11-02')?.bookId, 'new')
  assert.equal(bookOfRound(items, 't2', '2026-11-02'), undefined)
  assert.equal(memoryBookPolling(items), true)
  assert.equal(memoryBookPolling([items[1]]), false)
  const err = (code: string) => new ApiError({ status: 403, code, title: 'x' })
  assert.match(memoryBookFailure(err('PREMIUM_REQUIRED'))!, /프리미엄/)
  assert.match(memoryBookFailure(err('STUDENT_RECORDS_PRIVATE'))!, /답 보여 주기를 켜야/)
  assert.match(memoryBookFailure(err('STUDENT_RECORDS_PRIVATE'), 'PARENT')!, /아이가/)
  assert.equal(memoryBookFailure(err('SOMETHING_ELSE')), null)
  assert.equal(memoryBookFailure(new Error('x')), null)
})

// ---------------------------------------------------------------- 목업 계약

const handlers = [...memoryBookHandlers, ...retentionHandlers, ...serviceHandlers, ...parentHandlers, ...studentHandlers]
let token = ''
let childId = ''
async function call(path: string, body?: unknown, bearer = token) {
  const response = await getResponse(
    handlers,
    new Request('http://localhost/api/v1' + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { Authorization: 'Bearer ' + bearer, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    { baseUrl: 'http://localhost' },
  )
  assert.ok(response, path)
  const text = await response.text()
  return { status: response.status, data: text ? JSON.parse(text) : null }
}
const storage = new Map<string, string>()
test.beforeEach(async () => {
  storage.clear()
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: { getItem: (k: string) => storage.get(k) ?? null, setItem: (k: string, v: string) => storage.set(k, v), removeItem: (k: string) => storage.delete(k) },
  })
  resetRetention()
  resetMockMemoryBooks()
  setWorkspaceScenario('normal')
  await asParent()
  childId = (await call('/children')).data.items[0].childId as string
  setMockSubscription(childId, 'PREMIUM')
  saveSharing(childId, true)
  await asStudent()
})
/** 목업은 세션을 하나만 둔다: 학부모로 다시 로그인 */
async function asParent() {
  token = (await call('/auth/login', { email: 'parent@example.test', password: 'demo-only' }, '')).data.accessToken
}
async function asStudent() {
  await asParent()
  token = (await call('/auth/student-sessions', { childId })).data.accessToken
}

async function firstRound() {
  const album = (await call('/students/me/album')).data
  return { themeId: album.items[0].themeId as string, weekStart: album.items[0].weekStart as string }
}

test('목업: 유료·공개 학생은 202로 만들고, 같은 회차는 200으로 같은 그림책, 학부모도 목록을 본다', async () => {
  const round = await firstRound()
  const first = await call('/students/me/memory-books', { rounds: [round] })
  assert.equal(first.status, 202)
  assert.equal(readMemoryBook(first.data).status, 'QUEUED')
  const again = await call('/students/me/memory-books', { rounds: [round] })
  assert.equal(again.status, 200)
  assert.equal(again.data.bookId, first.data.bookId)
  assert.equal((await call(`/students/me/memory-books/${first.data.bookId}/download`)).data.code, 'MEMORY_BOOK_NOT_READY')
  await asParent()
  const parentList = readMemoryBookPage((await call(`/children/${childId}/memory-books`)).data)
  assert.equal(parentList.items[0].bookId, first.data.bookId)
})

test('목업: 무료 403, 비공개 403, 미보유 404, 회차 검사 400', async () => {
  const round = await firstRound()
  saveSharing(childId, false)
  assert.equal((await call('/students/me/memory-books', { rounds: [round] })).data.code, 'STUDENT_RECORDS_PRIVATE')
  await asParent()
  assert.equal((await call(`/children/${childId}/memory-books`)).data.code, 'STUDENT_RECORDS_PRIVATE')
  await asStudent()
  saveSharing(childId, true)
  setMockSubscription(childId, 'FREE')
  assert.equal((await call('/students/me/memory-books', { rounds: [round] })).data.code, 'PREMIUM_REQUIRED')
  setMockSubscription(childId, 'PREMIUM')
  assert.equal((await call('/students/me/memory-books', { rounds: [{ ...round, themeId: 'not-owned' }] })).status, 404)
  assert.equal((await call('/students/me/memory-books', { rounds: [] })).status, 400)
  storage.set(MOCK_MEMORY_BOOK_SCENARIO_KEY, 'FAIL')
  assert.equal((await call('/students/me/memory-books', { rounds: [round] })).status, 202)
})
