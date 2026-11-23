import { ApiError } from '../data/apiClient.ts'

/**
 * 추억 그림책 (docs/proposals/memory-book.md 7.1, 미도입 시험 구현, feature/memory-book 브랜치 전용).
 * 학부모만 발급(2026-11-23 결정), 원문 공개 자녀만(D2), 유료 구독(features.memoryBook), 회차 1개(D3).
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
    throw new ApiError({ status: 410, code: 'DOWNLOAD_EXPIRED', title: '받기 주소가 만료되었습니다. 다시 눌러 주세요.', retryable: true })
  return { url, expiresAt }
}

/** 발급 화면의 회차(자녀의 보유 액자)와 그 회차의 가장 최근 그림책 */
export type MemoryBookRoundItem = { themeId: string; weekStart: string; title: string; imageUrl: string | null; book: MemoryBook | null }
export type MemoryBookRoundPage = { items: MemoryBookRoundItem[]; page: number; size: number; totalElements: number }

export function readMemoryBookRoundPage(value: unknown): MemoryBookRoundPage {
  const v = record(value)
  if (!Array.isArray(v.items)) contract()
  const items = (v.items as unknown[]).map((item) => {
    const r = record(item)
    const weekStart = text(r.weekStart)
    if (!DATE.test(weekStart)) contract()
    if (typeof r.title !== 'string') contract()
    if (r.imageUrl != null && typeof r.imageUrl !== 'string') contract()
    return {
      themeId: text(r.themeId), weekStart, title: r.title as string,
      imageUrl: (r.imageUrl as string | null | undefined) ?? null,
      book: r.book == null ? null : readMemoryBook(r.book),
    }
  })
  return { items, page: count(v.page), size: count(v.size), totalElements: count(v.totalElements) }
}

/** 만드는 중이면 몇 초마다 다시 본다 */
export const MEMORY_BOOK_POLL_MS = 3000
export const memoryBookPolling = (rounds: MemoryBookRoundItem[] | undefined) => rounds?.some((r) => r.book?.status === 'QUEUED') ?? false

/** 공개 오류 코드 → 학부모에게 보일 말. 모르는 오류는 null(일반 오류 안내) */
export function memoryBookFailure(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null
  switch (error.problem.code) {
    case 'PREMIUM_REQUIRED': return '추억 그림책은 프리미엄 이용권에서 발급할 수 있습니다.'
    case 'STUDENT_RECORDS_PRIVATE': return '아이가 답 보여 주기를 켜야 그림책을 발급하고 볼 수 있습니다.'
    case 'USAGE_LIMIT_REACHED': return '오늘은 그림책을 더 발급할 수 없습니다. 내일 다시 시도해 주세요.'
    case 'THEME_FRAME_NOT_FOUND': return '아이가 아직 받지 않은 액자입니다.'
    case 'MEMORY_BOOK_NOT_READY': return '그림책을 만들고 있습니다. 잠시만 기다려 주세요.'
    case 'MEMORY_BOOK_FAILED': return '그림책을 만들지 못했습니다. 다시 발급해 주세요.'
    case 'MEMORY_BOOK_EXPIRED': return '보관 기간이 지난 그림책입니다. 다시 발급할 수 있습니다.'
    case 'DOWNLOAD_EXPIRED': return error.problem.title
    default: return null
  }
}
