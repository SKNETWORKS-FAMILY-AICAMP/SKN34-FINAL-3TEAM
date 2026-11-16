import { http } from 'msw/http'
import { ApiError } from '../../data/apiClient.ts'
import { MEMORY_CARD_MAX, MEMORY_EXPLANATION_ATTEMPTS_MAX, MEMORY_QUERY_MAX } from '../../domain/memory.ts'
import { framesOf } from '../fixtures/retention.ts'
import type { MockFrame } from '../fixtures/retention.ts'
import { guard, mockLatestAttempt, mockStudent, mockStudentHome, respond } from './student.ts'

/**
 * 추억 검색·설명 목업 (API 명세 2.12, P27, #567). 앨범 목업 회차(framesOf)를 검색 문서로 쓴다.
 * 벡터 검색은 흉내 내지 않고 질문 낱말이 회차·문제·답에 들어 있으면 찾은 것으로 본다. 답은 가상 문장이다.
 *
 * 상태 확인: 개발 도구에서 sessionStorage에 아래 키로 값을 넣는다.
 * - SEARCH_DOWN: 검색 503 / EXPLAIN_DOWN: 설명 503(횟수 안 셈)
 * - EXPLAIN_FAILED: 설명 FAILED / EXPLAIN_INSUFFICIENT: 설명 INSUFFICIENT(둘 다 횟수 셈)
 * 기록 없음은 기존 빈 앨범 키(MOCK_ALBUM_EMPTY_KEY), 하루 한도는 검색 20·설명 10회를 실제로 센다.
 */
export const MOCK_MEMORY_SCENARIO_KEY = 'sagomungchi:msw-memory'
export type MockMemoryScenario = 'SEARCH_DOWN' | 'EXPLAIN_DOWN' | 'EXPLAIN_FAILED' | 'EXPLAIN_INSUFFICIENT'
const LIMITS = { SEARCH: 20, EXPLANATION: 10 } as const
const usage = new Map<string, number>()

function scenario(): MockMemoryScenario | null {
  try {
    return (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(MOCK_MEMORY_SCENARIO_KEY) : null) as MockMemoryScenario | null
  } catch {
    return null
  }
}
/** 시험용: 오늘 사용 횟수를 지운다 */
export const resetMemoryUsage = () => usage.clear()

const fail = (status: number, code: string, title: string, detail?: string): never => {
  throw new ApiError({ status, code, title, ...(detail ? { detail } : {}) })
}
const kstDay = () => new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10)
/** core처럼 먼저 세고 한도를 넘으면 되돌린 뒤 429. 장애(5xx)는 셈을 되돌린다 */
function count(studentId: string, kind: keyof typeof LIMITS) {
  const key = `${studentId}@${kind}@${kstDay()}`
  const next = (usage.get(key) ?? 0) + 1
  if (next > LIMITS[kind]) {
    const what = kind === 'SEARCH' ? '추억 검색' : '추억 설명'
    return fail(429, 'USAGE_LIMIT_REACHED', '오늘 이용 한도에 도달했어요.', `${what}은 하루 ${LIMITS[kind]}회까지예요. 내일 0시(KST)에 초기화돼요.`)
  }
  usage.set(key, next)
  return () => usage.set(key, next - 1)
}

async function body(request: Request): Promise<Record<string, unknown>> {
  try {
    const v = (await request.json()) as unknown
    if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>
  } catch {
    /* 아래에서 400 */
  }
  return fail(400, 'VALIDATION_FAILED', '요청 형식이 올바르지 않아요.')
}
function query(v: Record<string, unknown>) {
  const q = typeof v.query === 'string' ? v.query.trim() : ''
  if (!q || (v.query as string).length > MEMORY_QUERY_MAX) return fail(400, 'VALIDATION_FAILED', '질문은 1~200자로 써 주세요.')
  return q
}

interface Doc { frame: MockFrame; missionId: string; title: string; attemptId: string; answerExcerpt: string }
/** 회차 문제마다 문서 1건. 시도가 없는 가상 회차 문제는 가상 시도 ID를 둔다 */
function docsOf(studentId: string, frames: MockFrame[]): Doc[] {
  return frames.flatMap((frame) => frame.missions.map((m) => ({
    frame,
    missionId: m.missionId,
    title: m.title,
    attemptId: mockLatestAttempt(studentId, m.missionId) ?? `mock-memory-${frame.themeId}-${m.day}`,
    answerExcerpt: `「${m.title}」에서 까닭을 들어 내 생각을 썼어요.(가상 답)`,
  })))
}
/** 낱말이 문서에 있으면 맞은 것으로 본다. 조사 하나 정도는 떼고 비교한다 */
function matchRatio(q: string, doc: Doc) {
  const haystack = `${doc.frame.title} ${doc.title} ${doc.answerExcerpt}`
  const words = q.split(/\s+/).filter((w) => w.length >= 2)
  if (!words.length) return 0
  const hit = words.filter((w) => haystack.includes(w) || (w.length >= 3 && haystack.includes(w.slice(0, -1))))
  return hit.length / words.length
}

export const memoryHandlers = [
  http.post('/api/v1/students/me/memories/search', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const q = query(await body(request))
      const undo = count(me.id, 'SEARCH')
      if (scenario() === 'SEARCH_DOWN') {
        undo()
        return fail(503, 'AI_UNAVAILABLE', '추억을 찾지 못했어요. 잠시 뒤 다시 해 주세요.')
      }
      const frames = framesOf(me.id, (await mockStudentHome(me)).missions)
      if (!frames.length) return { state: 'NO_RECORDS', cards: [] }
      const hits = docsOf(me.id, frames).map((doc) => ({ doc, score: matchRatio(q, doc) })).filter((h) => h.score > 0)
      const byRound = new Map<string, typeof hits>()
      for (const h of hits.sort((a, b) => b.score - a.score)) {
        const key = `${h.doc.frame.themeId}@${h.doc.frame.weekStart}`
        byRound.set(key, [...(byRound.get(key) ?? []), h])
      }
      const cards = [...byRound.values()].slice(0, MEMORY_CARD_MAX).map((group) => ({
        themeId: group[0].doc.frame.themeId,
        weekStart: group[0].doc.frame.weekStart,
        title: group[0].doc.frame.title,
        imageUrl: null,
        missions: group.slice(0, 5).map(({ doc }) => ({ missionId: doc.missionId, title: doc.title, attemptId: doc.attemptId, answerExcerpt: doc.answerExcerpt })),
        score: Math.round((0.35 + 0.5 * group[0].score) * 1000) / 1000,
      }))
      return { state: cards.length ? 'RESULTS' : 'NO_RESULTS', cards }
    }),
  ),

  http.post('/api/v1/students/me/memories/explanations', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const v = await body(request)
      query(v)
      const ids = v.attemptIds
      if (!Array.isArray(ids) || ids.length < 1 || ids.length > MEMORY_EXPLANATION_ATTEMPTS_MAX ||
          ids.some((x) => typeof x !== 'string' || !x) || new Set(ids).size !== ids.length)
        return fail(400, 'VALIDATION_FAILED', '설명할 기록을 1~3개 골라 주세요.')
      const undo = count(me.id, 'EXPLANATION')
      if (scenario() === 'EXPLAIN_DOWN') {
        undo()
        return fail(503, 'AI_UNAVAILABLE', '설명을 만들지 못했어요. 잠시 뒤 다시 해 주세요.')
      }
      const docs = docsOf(me.id, framesOf(me.id, (await mockStudentHome(me)).missions))
      const picked = (ids as string[]).map((attemptId) => docs.find((d) => d.attemptId === attemptId))
      // core는 learning 422를 그대로 전달하고 횟수에 넣는다(9.1)
      if (picked.some((d) => !d)) return fail(422, 'VALIDATION_FAILED', '내 추억 기록이 아니에요.')
      if (scenario() === 'EXPLAIN_FAILED') return { state: 'FAILED', text: null, citations: [] }
      if (scenario() === 'EXPLAIN_INSUFFICIENT') return { state: 'INSUFFICIENT', text: null, citations: [] }
      const evidence = picked as Doc[]
      // 근거 밖 활동·감정·능력 추정 없이 근거에 있는 사실만, 문장마다 번호(ai #565 모양)
      const sentences = evidence.map((d, i) => `${d.frame.weekStart} 주 「${d.frame.title}」에서 「${d.title}」 문제를 풀었어요[${i + 1}].`)
      if (sentences.length === 1) sentences.push(`그때 답에 까닭을 들어 생각을 썼어요[1].`)
      return {
        state: 'GENERATED',
        text: sentences.join(' '),
        citations: evidence.map((d, i) => ({ no: i + 1, themeId: d.frame.themeId, weekStart: d.frame.weekStart, attemptId: d.attemptId })),
      }
    }),
  ),
]
