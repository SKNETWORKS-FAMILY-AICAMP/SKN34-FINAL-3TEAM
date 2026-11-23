import { ApiError } from '../data/apiClient.ts'

/**
 * 추억 그림책 (docs/proposals/memory-book.md 7.1, 미도입 시험 구현, feature/memory-book 브랜치 전용).
 * 원문 공개 학생만(D2), 유료 구독(features.memoryBook), 회차 1개(D3).
 */
export type MemoryBookStatus = 'QUEUED' | 'READY' | 'FAILED' | 'EXPIRED'
export type MemoryBookRound = { themeId: string; weekStart: string }
export type MemoryBook = {
  bookId: string
  status: MemoryBookStatus
  failureCode: string | null
  rounds: MemoryBookRound[]
  createdAt: string
  completedAt: string | null
  expiresAt: string
}
export type MemoryBookPage = { items: MemoryBook[]; page: number; size: number; totalElements: number }
export type MemoryBookDownload = { url: string; expiresAt: string }

const STATUSES: MemoryBookStatus[] = ['QUEUED', 'READY', 'FAILED', 'EXPIRED']
const DATE = /^\d{4}-\d{2}-\d{2}$/

function contract(): never {
  throw new ApiError({ status: 502, code: 'CONTRACT_INVALID', title: '그림책 정보를 확인하지 못했어요.', retryable: true })
}
const record = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : contract())
const text = (v: unknown): string => (typeof v === 'string' && v.length > 0 ? v : contract())
const time = (v: unknown): string => (typeof v === 'string' && !Number.isNaN(Date.parse(v)) ? v : contract())
const count = (v: unknown): number => (typeof v === 'number' && Number.isInteger(v) && v >= 0 ? v : contract())

export function readMemoryBook(value: unknown): MemoryBook {
  const v = record(value)
  const status = STATUSES.find((s) => s === v.status) ?? contract()
  if (!Array.isArray(v.rounds) || v.rounds.length < 1) contract()
  const rounds = (v.rounds as unknown[]).map((r) => {
    const round = record(r)
    const weekStart = text(round.weekStart)
    if (!DATE.test(weekStart)) contract()
    return { themeId: text(round.themeId), weekStart }
  })
  const failureCode = v.failureCode == null ? null : text(v.failureCode)
  return {
    bookId: text(v.bookId), status, failureCode, rounds,
    createdAt: time(v.createdAt), completedAt: v.completedAt == null ? null : time(v.completedAt), expiresAt: time(v.expiresAt),
  }
}

export function readMemoryBookPage(value: unknown): MemoryBookPage {
  const v = record(value)
  if (!Array.isArray(v.items)) contract()
  return { items: (v.items as unknown[]).map(readMemoryBook), page: count(v.page), size: count(v.size), totalElements: count(v.totalElements) }
}

/** 내려받기 주소는 http(s)이고 아직 만료되지 않았을 때만 연다 */
export function readMemoryBookDownload(value: unknown, now = Date.now()): MemoryBookDownload {
  const v = record(value)
  const url = text(v.url)
  const expiresAt = time(v.expiresAt)
  let protocol = ''
  try { protocol = new URL(url, 'https://base.invalid').protocol } catch { contract() }
  if (!['http:', 'https:'].includes(protocol)) contract()
  if (Date.parse(expiresAt) <= now)
    throw new ApiError({ status: 410, code: 'DOWNLOAD_EXPIRED', title: '받기 주소가 만료되었어요. 다시 눌러 주세요.', retryable: true })
  return { url, expiresAt }
}

/** 그 회차의 가장 최근 그림책(목록은 최근순) */
export const bookOfRound = (books: MemoryBook[] | undefined, themeId: string, weekStart: string) =>
  books?.find((b) => b.rounds.some((r) => r.themeId === themeId && r.weekStart === weekStart))

/** 만드는 중이면 몇 초마다 다시 본다 */
export const MEMORY_BOOK_POLL_MS = 3000
export const memoryBookPolling = (books: MemoryBook[] | undefined) => books?.some((b) => b.status === 'QUEUED') ?? false

/** 공개 오류 코드 → 아이·학부모에게 보일 말. 모르는 오류는 null(일반 오류 안내) */
export function memoryBookFailure(error: unknown, audience: 'STUDENT' | 'PARENT' = 'STUDENT'): string | null {
  if (!(error instanceof ApiError)) return null
  switch (error.problem.code) {
    case 'PREMIUM_REQUIRED': return audience === 'STUDENT' ? '그림책은 프리미엄 이용권에서 만들 수 있어요.' : '추억 그림책은 프리미엄 이용권에서 만들 수 있어요.'
    case 'STUDENT_RECORDS_PRIVATE': return audience === 'STUDENT'
      ? '그림책을 만들려면 보호자에게 답 보여 주기를 켜야 해요.'
      : '아이가 답 보여 주기를 켜야 그림책을 볼 수 있어요.'
    case 'USAGE_LIMIT_REACHED': return '오늘은 그림책을 더 만들 수 없어요. 내일 다시 만들어 주세요.'
    case 'THEME_FRAME_NOT_FOUND': return '아직 받지 않은 액자예요.'
    case 'MEMORY_BOOK_NOT_READY': return '그림책을 만들고 있어요. 조금만 기다려 주세요.'
    case 'MEMORY_BOOK_FAILED': return '그림책을 만들지 못했어요. 다시 만들어 주세요.'
    case 'MEMORY_BOOK_EXPIRED': return '보관 기간이 지난 그림책이에요. 다시 만들 수 있어요.'
    case 'DOWNLOAD_EXPIRED': return error.problem.title
    default: return null
  }
}
