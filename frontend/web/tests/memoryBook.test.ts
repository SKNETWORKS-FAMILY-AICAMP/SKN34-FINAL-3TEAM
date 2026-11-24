import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { memoryBookHandlers, MOCK_MEMORY_BOOK_LOCKED_KEY, MOCK_MEMORY_BOOK_SCENARIO_KEY, resetMockMemoryBooks } from '../src/mocks/handlers/memoryBook.ts'
import { retentionHandlers } from '../src/mocks/handlers/retention.ts'
import { serviceHandlers } from '../src/mocks/handlers/service.ts'
import { parentHandlers } from '../src/mocks/handlers/parent.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { resetRetention } from '../src/mocks/fixtures/retention.ts'
import { saveSharing } from '../src/mocks/fixtures/sharing.ts'
import { setMockSubscription } from '../src/mocks/fixtures/payments.ts'
import { ApiError } from '../src/data/apiClient.ts'
import { memoryBookLabel } from '../src/domain/payment.ts'
import {
  memoryBookFailedReason,
  memoryBookFailure,
  memoryBookLockedNotice,
  memoryBookPolling,
  memoryBookShelfLocked,
  readMemoryBook,
  readMemoryBookDownload,
  readMemoryBookPage,
  readMemoryBookRoundPage,
} from '../src/domain/memoryBook.ts'

// 추억 그림책 (docs/proposals/memory-book.md): 학부모만 발급. 응답 읽기·오류 문구와 목업 계약. 가상 값만 쓴다.

const book = (over: Record<string, unknown> = {}) => ({
  bookId: 'b1', status: 'READY', failureCode: null, rounds: [{ themeId: 't1', weekStart: '2026-11-02' }],
  createdAt: '2026-11-23T00:00:00Z', completedAt: '2026-11-23T00:00:05Z', expiresAt: '2026-12-23T00:00:00Z', ...over,
})
const round = (over: Record<string, unknown> = {}) => ({ themeId: 't1', weekStart: '2026-11-02', title: '등대 불빛', imageUrl: null, book: null, ...over })

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

test('발급 화면 회차 목록은 회차마다 최근 그림책(없으면 null)을 읽는다', () => {
  const page = readMemoryBookRoundPage({ items: [round(), round({ themeId: 't2', book: book({ status: 'QUEUED' }) })], page: 0, size: 50, totalElements: 2 })
  assert.equal(page.items[0].book, null)
  assert.equal(page.items[1].book?.status, 'QUEUED')
  assert.equal(memoryBookPolling(page.items), true)
  assert.equal(memoryBookPolling([page.items[0]]), false)
  for (const bad of [round({ weekStart: '11/02' }), round({ title: 3 }), round({ imageUrl: 5 }), round({ book: book({ status: 'X' }) })])
    assert.throws(() => readMemoryBookRoundPage({ items: [bad], page: 0, size: 50, totalElements: 1 }), /확인하지 못/)
})

test('받기 주소는 http(s)이고 만료 전일 때만 쓴다', () => {
  const now = Date.parse('2026-11-23T00:00:00Z')
  assert.equal(readMemoryBookDownload({ url: 'https://files.test/b.pdf', expiresAt: '2026-11-23T00:05:00Z' }, now).url, 'https://files.test/b.pdf')
  assert.equal(readMemoryBookDownload({ url: '/demo/memory-book-sample.pdf', expiresAt: '2026-11-23T00:05:00Z' }, now).url, '/demo/memory-book-sample.pdf')
  assert.throws(() => readMemoryBookDownload({ url: 'javascript:alert(1)', expiresAt: '2026-11-23T00:05:00Z' }, now), /확인하지 못/)
  assert.throws(() => readMemoryBookDownload({ url: 'https://files.test/b.pdf', expiresAt: '2026-11-22T23:59:00Z' }, now), /만료/)
})

test('오류 문구는 학부모 말로', () => {
  const err = (code: string) => new ApiError({ status: 403, code, title: 'x' })
  assert.match(memoryBookFailure(err('PREMIUM_REQUIRED'))!, /프리미엄/)
  assert.match(memoryBookFailure(err('STUDENT_RECORDS_PRIVATE'))!, /아이가 답 보여 주기를 켜야/)
  assert.equal(memoryBookFailure(err('SOMETHING_ELSE')), null)
  assert.equal(memoryBookFailure(new Error('x')), null)
})

// ---------------------------------------------------------------- 목업 계약

const handlers = [...memoryBookHandlers, ...retentionHandlers, ...serviceHandlers, ...parentHandlers, ...studentHandlers]
let token = ''
let childId = ''
test('책장 회차 목록(#1000): lockedCount·canCreate를 읽고, #999 전처럼 없으면 숨긴 0·발급 여부 모름', () => {
  const base = { items: [round()], page: 0, size: 50, totalElements: 1 }
  const free = readMemoryBookRoundPage({ ...base, lockedCount: 3, canCreate: false })
  assert.deepEqual([free.lockedCount, free.canCreate, memoryBookShelfLocked(free)], [3, false, true])
  const paid = readMemoryBookRoundPage({ ...base, lockedCount: 0, canCreate: true })
  assert.equal(memoryBookShelfLocked(paid), false)
  const before = readMemoryBookRoundPage(base)
  assert.deepEqual([before.lockedCount, before.canCreate, memoryBookShelfLocked(before)], [0, null, false])
  for (const bad of [{ lockedCount: -1 }, { lockedCount: 1.5 }, { lockedCount: '2' }, { canCreate: 'no' }, { canCreate: 0 }])
    assert.throws(() => readMemoryBookRoundPage({ ...base, ...bad }), /확인하지 못/)
})

test('책장 잠금 안내: 숨긴 회차가 있으면 그 수, 없으면 프리미엄에서 할 수 있는 것', () => {
  assert.equal(memoryBookLockedNotice(2), '지난 그림책 2권은 프리미엄에서 볼 수 있어요.')
  assert.equal(memoryBookLockedNotice(0), '그림책 만들기와 지난 그림책 모아 보기는 프리미엄에서 할 수 있어요.')
})

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
async function asParent() {
  token = ''
  token = (await call('/auth/login', { email: 'parent@example.test', password: 'demo-only' })).data.accessToken
}
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
})

test('목업: 학부모가 회차 목록에서 202로 발급, 같은 회차는 200으로 같은 그림책, 목록에 붙는다', async () => {
  const rounds = readMemoryBookRoundPage((await call(`/children/${childId}/memory-books/rounds`)).data)
  assert.ok(rounds.items.length >= 1)
  assert.equal(rounds.items[0].book, null)
  const target = { themeId: rounds.items[0].themeId, weekStart: rounds.items[0].weekStart }
  const first = await call(`/children/${childId}/memory-books`, { rounds: [target] })
  assert.equal(first.status, 202)
  assert.equal(readMemoryBook(first.data).status, 'QUEUED')
  const again = await call(`/children/${childId}/memory-books`, { rounds: [target] })
  assert.equal(again.status, 200)
  assert.equal(again.data.bookId, first.data.bookId)
  assert.equal((await call(`/children/${childId}/memory-books/${first.data.bookId}/download`)).data.code, 'MEMORY_BOOK_NOT_READY')
  const after = readMemoryBookRoundPage((await call(`/children/${childId}/memory-books/rounds`)).data)
  assert.equal(after.items[0].book?.bookId, first.data.bookId)
  assert.equal(readMemoryBookPage((await call(`/children/${childId}/memory-books`)).data).items[0].bookId, first.data.bookId)
})

test('목업: 무료 403, 비공개 403, 미보유 404, 회차 검사 400, 학생 경로 없음', async () => {
  const target = (({ themeId, weekStart }) => ({ themeId, weekStart }))(
    readMemoryBookRoundPage((await call(`/children/${childId}/memory-books/rounds`)).data).items[0])
  saveSharing(childId, false)
  assert.equal((await call(`/children/${childId}/memory-books`, { rounds: [target] })).data.code, 'STUDENT_RECORDS_PRIVATE')
  assert.equal((await call(`/children/${childId}/memory-books/rounds`)).data.code, 'STUDENT_RECORDS_PRIVATE')
  saveSharing(childId, true)
  setMockSubscription(childId, 'FREE')
  assert.equal((await call(`/children/${childId}/memory-books`, { rounds: [target] })).data.code, 'PREMIUM_REQUIRED')
  setMockSubscription(childId, 'PREMIUM')
  assert.equal((await call(`/children/${childId}/memory-books`, { rounds: [{ ...target, themeId: 'not-owned' }] })).status, 404)
  assert.equal((await call(`/children/${childId}/memory-books`, { rounds: [] })).status, 400)
  storage.set(MOCK_MEMORY_BOOK_SCENARIO_KEY, 'FAIL')
  assert.equal((await call(`/children/${childId}/memory-books`, { rounds: [target] })).status, 202)
  assert.notEqual((await call('/students/me/memory-books', { rounds: [target] })).status, 202)
})

test('요금제 상품 설명: 유료 상품에 추억 그림책과 하루 권 수를 붙이고, 끈 상품·무료에는 붙이지 않는다(B4)', () => {
  assert.equal(memoryBookLabel({ price: 14900, features: { memoryBook: true }, limits: { dailyMemoryBooks: 3 } }), ' · 추억 그림책 하루 3권')
  assert.equal(memoryBookLabel({ price: 14900, features: {}, limits: {} }), ' · 추억 그림책')
  assert.equal(memoryBookLabel({ price: 14900, features: { memoryBook: false }, limits: { dailyMemoryBooks: 3 } }), '')
  assert.equal(memoryBookLabel({ price: 0, features: {}, limits: { dailyMemoryBooks: 3 } }), '')
  assert.equal(memoryBookLabel({ price: 14900, features: { memoryBook: true }, limits: { dailyMemoryBooks: 0 } }), '')
  assert.equal(memoryBookLabel({ price: 14900, features: { memoryBook: 'yes' }, limits: {} }), '')
})

test('실패한 그림책 이유: 그림을 한 장도 받지 못한 실패는 따로 안내한다(#975)', () => {
  assert.equal(memoryBookFailedReason('ASSET_UNAVAILABLE'), '그림을 불러오지 못해 만들지 못했습니다. 다시 발급해 주세요.')
  assert.equal(memoryBookFailedReason('INVALID_ROUND'), '지난 발급 실패')
  assert.equal(memoryBookFailedReason(null), '지난 발급 실패')
})

test('목업 책장(#999 계약): 유료는 전체·lockedCount 0·canCreate true, 무료는 끝난 최근 4주만·숨긴 수·canCreate false', async () => {
  const paid = readMemoryBookRoundPage((await call(`/children/${childId}/memory-books/rounds`)).data)
  assert.deepEqual([paid.lockedCount, paid.canCreate], [0, true])
  assert.ok(paid.items.length >= 1)
  setMockSubscription(childId, 'FREE')
  const free = readMemoryBookRoundPage((await call(`/children/${childId}/memory-books/rounds`)).data)
  assert.equal(free.canCreate, false)
  assert.equal(free.totalElements, free.items.length)
  // 목업 지난 액자는 1~3주 전뿐이라 모두 4주 안: 숨긴 회차 없음, 표지는 유료와 같은 수
  assert.deepEqual([free.items.length, free.lockedCount], [paid.items.length, 0])
  storage.set(MOCK_MEMORY_BOOK_LOCKED_KEY, '5')
  assert.equal(readMemoryBookRoundPage((await call(`/children/${childId}/memory-books/rounds`)).data).lockedCount, 5)
  setMockSubscription(childId, 'PREMIUM')
  assert.equal(readMemoryBookRoundPage((await call(`/children/${childId}/memory-books/rounds`)).data).lockedCount, 0)
})
