import { http } from 'msw/http'
import { ApiError } from '../../data/apiClient.ts'
import { framesOf } from '../fixtures/retention.ts'
import { requireShared } from '../fixtures/sharing.ts'
import { mockPremium } from '../fixtures/payments.ts'
import { respond } from './student.ts'
import { demoMissions } from '../../data/classroom/demoGateway.ts'
import { fixtureStore } from '../fixtures/student.ts'
import { parentChild } from './parent.ts'

/**
 * 추억 그림책 목업 (docs/proposals/memory-book.md 7.1, 미도입 시험 구현). 학부모만 발급한다. core 규칙을 흉내 낸다:
 * 원문 공개 학생만(403 STUDENT_RECORDS_PRIVATE), 프리미엄만(403 PREMIUM_REQUIRED), 보유 액자만(404), 하루 3개(429),
 * 같은 회차는 만드는 중·완성본을 재사용(200). 만들고 4초 뒤 완성(READY)으로 바뀐다. 받기 주소는 표본 PDF.
 *
 * 상태 확인: sessionStorage 'sagomungchi:msw-memory-book' = 'FAIL'이면 새 그림책이 만들기 실패(FAILED)로 끝난다.
 */
export const MOCK_MEMORY_BOOK_SCENARIO_KEY = 'sagomungchi:msw-memory-book'
const READY_AFTER_MS = 4000
const DAILY_LIMIT = 3
const SAMPLE_PDF = '/demo/memory-book-sample.pdf'

type MockBook = { bookId: string; studentId: string; themeId: string; weekStart: string; createdAt: number; fail: boolean }
const books: MockBook[] = []
const mockChildren = () => fixtureStore.children()
/** 시험용 */
export const resetMockMemoryBooks = () => { books.length = 0 }

const fail = (status: number, code: string, title: string): never => {
  throw new ApiError({ status, code, title })
}
const failing = () => {
  try { return typeof sessionStorage !== 'undefined' && sessionStorage.getItem(MOCK_MEMORY_BOOK_SCENARIO_KEY) === 'FAIL' } catch { return false }
}
const kstDay = (ms: number) => new Date(ms + 9 * 3600_000).toISOString().slice(0, 10)

function view(b: MockBook, now = Date.now()) {
  const done = now - b.createdAt >= READY_AFTER_MS
  const status = !done ? 'QUEUED' : b.fail ? 'FAILED' : 'READY'
  return {
    bookId: b.bookId,
    status,
    failureCode: status === 'FAILED' ? 'RENDER_FAILED' : null,
    rounds: [{ themeId: b.themeId, weekStart: b.weekStart }],
    createdAt: new Date(b.createdAt).toISOString(),
    completedAt: done ? new Date(b.createdAt + READY_AFTER_MS).toISOString() : null,
    expiresAt: new Date(b.createdAt + 30 * 86400_000).toISOString(),
  }
}
const pageOf = (studentId: string) => {
  const items = books.filter((b) => b.studentId === studentId).sort((a, b) => b.createdAt - a.createdAt).map((b) => view(b))
  return { items, page: 0, size: 50, totalElements: items.length }
}
function downloadOf(studentId: string, bookId: string) {
  const b = books.find((x) => x.bookId === bookId && x.studentId === studentId) ?? fail(404, 'MEMORY_BOOK_NOT_FOUND', '그림책을 찾을 수 없어요.')
  const v = view(b)
  if (v.status === 'QUEUED') fail(409, 'MEMORY_BOOK_NOT_READY', '그림책을 만들고 있어요.')
  if (v.status === 'FAILED') fail(409, 'MEMORY_BOOK_FAILED', '그림책을 만들지 못했어요.')
  return { url: SAMPLE_PDF, expiresAt: new Date(Date.now() + 300_000).toISOString() }
}

async function round(request: Request) {
  let v: unknown
  try { v = await request.json() } catch { v = null }
  const rounds = (v as { rounds?: unknown } | null)?.rounds
  if (!Array.isArray(rounds) || rounds.length !== 1) return fail(400, 'VALIDATION_FAILED', 'rounds는 회차 1개 배열이어야 합니다.')
  const r = rounds[0] as { themeId?: unknown; weekStart?: unknown }
  if (typeof r.themeId !== 'string' || typeof r.weekStart !== 'string' || new Date(`${r.weekStart}T00:00:00Z`).getUTCDay() !== 1)
    return fail(400, 'VALIDATION_FAILED', '회차를 확인해 주세요.')
  return { themeId: r.themeId, weekStart: r.weekStart }
}

/** 학부모 요청이라 학생 홈을 부를 수 없어, 앨범 목업과 같은 학년 데모 미션으로 회차를 만든다(이미 있으면 그대로) */
async function framesOfChild(childId: string) {
  const child = (await mockChildren()).find((c) => c.id === childId)
  return child ? framesOf(child.id, demoMissions(child.grade)) : []
}

export const memoryBookHandlers = [
  http.get('/api/v1/children/:childId/memory-books/rounds', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      requireShared(c.id)
      const now = Date.now()
      const items = (await framesOfChild(c.id)).map((f) => {
        const latest = books.filter((b) => b.studentId === c.id && b.themeId === f.themeId && b.weekStart === f.weekStart)
          .sort((a, b) => b.createdAt - a.createdAt)[0]
        return { themeId: f.themeId, weekStart: f.weekStart, title: f.title, imageUrl: null, book: latest ? view(latest, now) : null }
      })
      return { items, page: 0, size: 50, totalElements: items.length }
    }),
  ),
  http.post('/api/v1/children/:childId/memory-books', async ({ request, params }) => {
    let created = true
    return respond(async () => {
      const c = await parentChild(request, String(params.childId))
      const r = await round(request)
      requireShared(c.id)
      const now = Date.now()
      const existing = books.find((b) => b.studentId === c.id && b.themeId === r.themeId && b.weekStart === r.weekStart && view(b, now).status !== 'FAILED')
      if (existing) { created = false; return view(existing, now) }
      const owned = (await framesOfChild(c.id)).some((f) => f.themeId === r.themeId && f.weekStart === r.weekStart)
      if (!owned) return fail(404, 'THEME_FRAME_NOT_FOUND', '아직 받지 않은 기념 액자예요.')
      if (books.filter((b) => b.studentId === c.id && kstDay(b.createdAt) === kstDay(now)).length >= DAILY_LIMIT)
        return fail(429, 'USAGE_LIMIT_REACHED', '오늘은 추억 그림책을 더 만들 수 없어요.')
      if (!mockPremium(c.id)) return fail(403, 'PREMIUM_REQUIRED', '추억 그림책은 프리미엄 이용권에서 만들 수 있어요.')
      const book = { bookId: crypto.randomUUID(), studentId: c.id, ...r, createdAt: now, fail: failing() }
      books.push(book)
      return view(book, now)
    }).then((response) => (created ? new Response(response.body, { status: response.status === 200 ? 202 : response.status, headers: response.headers }) : response))
  }),
  http.get('/api/v1/children/:childId/memory-books', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      requireShared(c.id)
      return pageOf(c.id)
    }),
  ),
  http.get('/api/v1/children/:childId/memory-books/:bookId/download', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      requireShared(c.id)
      return downloadOf(c.id, String(params.bookId))
    }),
  ),
]
