/**
 * 추억 검색·설명 (P27, API 명세 2.12, FN-RET-12·13, #567).
 * 화면(#589 새 디자인 확정 뒤)과 무관한 응답 읽기·규칙만 둔다. 서버 응답은 여기서 검사해 모르는 값이 화면을 깨지 않게 한다.
 */

/** 질문 글자 수 상한(core·learning 1~200자) */
export const MEMORY_QUERY_MAX = 200
/** 검색 결과 카드 최대 개수(2026-11-13 확정) */
export const MEMORY_CARD_MAX = 3
/** 설명 요청에 보내는 시도 최대 개수(2.12) */
export const MEMORY_EXPLANATION_ATTEMPTS_MAX = 3

export type MemorySearchState = 'RESULTS' | 'NO_RESULTS' | 'NO_RECORDS'
export interface MemoryMission {
  missionId: string
  title: string
  /** 설명 요청에 쓰는 시도 */
  attemptId: string
  answerExcerpt: string
}
export interface MemoryCard {
  themeId: string
  weekStart: string
  title: string
  imageUrl: string | null
  /** learning이 관련도 높은 순으로 준다 */
  missions: MemoryMission[]
  score: number
}
export interface MemorySearch {
  state: MemorySearchState
  cards: MemoryCard[]
}

export type MemoryExplanationState = 'GENERATED' | 'INSUFFICIENT' | 'FAILED'
export interface MemoryCitation {
  no: number
  themeId: string
  weekStart: string
  attemptId: string
}
export interface MemoryExplanation {
  state: MemoryExplanationState
  /** GENERATED일 때만 글이 있고 문장 끝마다 근거 번호 "[1]"이 붙어 온다 */
  text: string | null
  citations: MemoryCitation[]
}
export interface ExplanationSentence {
  /** 근거 번호를 뺀 문장 */
  text: string
  citations: MemoryCitation[]
}

const SEARCH_STATES: readonly string[] = ['RESULTS', 'NO_RESULTS', 'NO_RECORDS']
const EXPLANATION_STATES: readonly string[] = ['GENERATED', 'INSUFFICIENT', 'FAILED']
const searchContractError = (): never => {
  throw new Error('추억을 찾은 결과를 확인하지 못했어요. 다시 확인해 주세요.')
}
const explanationContractError = (): never => {
  throw new Error('추억 설명을 확인하지 못했어요. 다시 확인해 주세요.')
}
const id = (v: unknown): v is string => typeof v === 'string' && v.length > 0
const isoDate = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)
const plain = (v: unknown) => (typeof v === 'string' ? v : '')
const MARKS = /((?:\[\d+\])+)/
const MARK = /\[(\d+)\]/g

/** 앞뒤 공백을 뺀 질문. 비었거나 200자를 넘으면 null(보내지 않음, core 400과 같은 규칙) */
export function memoryQuery(raw: string): string | null {
  const q = raw.trim()
  return q.length >= 1 && q.length <= MEMORY_QUERY_MAX ? q : null
}

export function readMemorySearch(raw: unknown): MemorySearch {
  const v = (raw ?? {}) as Record<string, unknown>
  if (typeof v.state !== 'string' || !SEARCH_STATES.includes(v.state) || !Array.isArray(v.cards) || v.cards.length > MEMORY_CARD_MAX)
    return searchContractError()
  const state = v.state as MemorySearchState
  // 결과가 있다는데 카드가 없거나, 없다는데 카드가 오면 어느 쪽을 믿을지 알 수 없다
  if ((state === 'RESULTS') !== (v.cards.length > 0)) return searchContractError()
  const cards = v.cards.map((x): MemoryCard => {
    const c = (x ?? {}) as Record<string, unknown>
    if (!id(c.themeId) || !isoDate(c.weekStart) || typeof c.score !== 'number' || !Number.isFinite(c.score) ||
        !Array.isArray(c.missions) || c.missions.length === 0) return searchContractError()
    return {
      themeId: c.themeId,
      weekStart: c.weekStart,
      title: plain(c.title),
      imageUrl: id(c.imageUrl) ? c.imageUrl : null,
      score: c.score,
      missions: c.missions.map((y): MemoryMission => {
        const m = (y ?? {}) as Record<string, unknown>
        if (!id(m.missionId) || !id(m.attemptId)) return searchContractError()
        return { missionId: m.missionId, attemptId: m.attemptId, title: plain(m.title), answerExcerpt: plain(m.answerExcerpt) }
      }),
    }
  })
  return { state, cards }
}

/**
 * 설명 요청에 보낼 시도: 카드마다 맨 앞(가장 관련 높은) 문제 1개, 최대 3개.
 * 근거는 카드 단위(결정 기록 3.5 "근거 구성(카드 최대 3개)")
 */
export function explanationAttempts(cards: MemoryCard[]): string[] {
  return [...new Set(cards.slice(0, MEMORY_EXPLANATION_ATTEMPTS_MAX).map((c) => c.missions[0].attemptId))]
}

/** sentAttemptIds는 요청에 보낸 시도. 그 밖의 시도를 가리키는 근거는 계약 위반으로 본다 */
export function readMemoryExplanation(raw: unknown, sentAttemptIds: readonly string[]): MemoryExplanation {
  const v = (raw ?? {}) as Record<string, unknown>
  if (typeof v.state !== 'string' || !EXPLANATION_STATES.includes(v.state)) return explanationContractError()
  const state = v.state as MemoryExplanationState
  // 근거 부족·실패는 글을 보여 주지 않는다(대체 문장 없음, FN-RET-13)
  if (state !== 'GENERATED') return { state, text: null, citations: [] }
  if (!id(v.text) || !v.text.trim() || !Array.isArray(v.citations) || v.citations.length === 0) return explanationContractError()
  const seen = new Set<number>()
  const citations = v.citations.map((x): MemoryCitation => {
    const c = (x ?? {}) as Record<string, unknown>
    if (!Number.isInteger(c.no) || Number(c.no) < 1 || Number(c.no) > sentAttemptIds.length || seen.has(Number(c.no)) ||
        !id(c.attemptId) || !sentAttemptIds.includes(c.attemptId) || !id(c.themeId) || !isoDate(c.weekStart))
      return explanationContractError()
    seen.add(Number(c.no))
    return { no: Number(c.no), themeId: c.themeId, weekStart: c.weekStart, attemptId: c.attemptId }
  })
  // 글 속 번호가 모두 근거 목록에 있어야 문장마다 근거 카드를 이을 수 있다
  for (const m of v.text.matchAll(MARK)) if (!seen.has(Number(m[1]))) return explanationContractError()
  return { state, text: v.text, citations }
}

/**
 * 설명 글을 문장으로 나누고 문장 끝 근거 번호를 근거에 잇는다(FN-RET-13 "문장마다 근거 카드").
 * ai가 만든 모양: `문장[1][2]. 다음 문장[3].`(번호는 문장부호 앞, 문장 사이 공백 하나, #565)
 */
export function explanationSentences(explanation: MemoryExplanation): ExplanationSentence[] {
  if (explanation.state !== 'GENERATED' || !explanation.text) return []
  const byNo = new Map(explanation.citations.map((c) => [c.no, c]))
  const parts = explanation.text.split(MARKS)
  const sentences: ExplanationSentence[] = []
  // split 결과: [본문, 번호들, 다음 문장부호+본문, 번호들, ...]
  let body = parts[0]
  for (let i = 1; i < parts.length; i += 2) {
    const after = parts[i + 1] ?? ''
    const punct = /^[.!?。…~]*/.exec(after)![0]
    const nos = [...parts[i].matchAll(MARK)].map((m) => Number(m[1]))
    const text = (body + punct).trim()
    if (text) sentences.push({ text, citations: nos.flatMap((no) => byNo.get(no) ?? []) })
    body = after.slice(punct.length)
  }
  if (body.trim()) sentences.push({ text: body.trim(), citations: [] })
  return sentences
}

/**
 * 검색·설명 오류를 안내 종류로 나눈다(2.12, 결정 기록 9.1·13.1).
 * - LIMIT: 429 오늘 횟수 다 씀(서버 detail에 내일 0시 초기화 문구)
 * - UNAVAILABLE: 5xx·연결 실패. "잠시 뒤 다시", 횟수 안 줄어듦
 * - INVALID: 400·422 입력 오류(400은 횟수 안 셈, 422는 셈)
 * - OTHER: 그 밖(로그인 만료 등은 apiClient가 따로 처리)
 */
export type MemoryFailureKind = 'LIMIT' | 'UNAVAILABLE' | 'INVALID' | 'OTHER'
export interface MemoryFailure {
  kind: MemoryFailureKind
  /** 이 실패가 오늘 횟수에 들어갔는지 */
  usageCounted: boolean
  /** 서버가 준 안내(있으면) */
  detail: string | null
}
export function memoryFailure(error: unknown): MemoryFailure {
  const p = (error as { problem?: { status?: unknown; detail?: unknown } } | null)?.problem
  const status = typeof p?.status === 'number' ? p.status : null
  const detail = typeof p?.detail === 'string' && p.detail ? p.detail : null
  // 응답 없이 끊긴 요청(fetch 실패)은 장애와 같이 안내한다
  if (status === null) return { kind: error instanceof TypeError ? 'UNAVAILABLE' : 'OTHER', usageCounted: false, detail: null }
  if (status === 429) return { kind: 'LIMIT', usageCounted: false, detail }
  if (status >= 500) return { kind: 'UNAVAILABLE', usageCounted: false, detail }
  if (status === 400) return { kind: 'INVALID', usageCounted: false, detail }
  if (status === 422) return { kind: 'INVALID', usageCounted: true, detail }
  return { kind: 'OTHER', usageCounted: false, detail }
}
