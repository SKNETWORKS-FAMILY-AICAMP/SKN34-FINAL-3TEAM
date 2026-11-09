import type { Metric, Period, PublicAttempt, ThinkingType, AnalysisVerification, AnalysisFallback, AnalysisNotice } from './classroom.ts'
import type { QueryState } from './queryState.ts'
export interface Page<T> {
  items: T[]
  page: number
  size: number
  totalElements: number
}
export interface ConsentDocument {
  documentId: string
  kind: 'TERMS' | 'PRIVACY' | 'GUARDIAN' | 'COMMUNITY'
  version: string
  title: string
  content: string
  required: boolean
}
/** 가입·계정 단위 필수 동의 문서(이용 안내·개인정보). 자녀 단위 법정대리인·선택 커뮤니티 동의는 빠진다. */
export const isAccountDocument = (d: Pick<ConsentDocument, 'kind'>) => d.kind === 'TERMS' || d.kind === 'PRIVACY'
export interface ConsentHistory {
  consentId: string
  subjectUserId: string
  studentId: string | null
  document: ConsentDocument
  agreed: boolean
  status: 'AGREED' | 'WITHDRAWN'
  agreedAt: string
  withdrawnAt: string | null
}
export interface Consent {
  documentId: string
  version: string
  agreed: boolean
}
export interface Scope extends Period {
  childId: string
  changed?: boolean
}
export interface Summary {
  childId: string
  state: QueryState
  period: Period
  inclusionRule: string
  metrics: Metric[]
}
export interface ThinkingActivity {
  type: ThinkingType
  state: QueryState
  missions: { attemptId: string; title: string }[]
  summary?: string
  itemId?: string
}
export interface ThinkingResponse {
  childId: string
  state: QueryState
  period: Period
  items: ThinkingActivity[]
}
export interface RecordPage extends Page<PublicAttempt> {
  childId: string
  state: QueryState
  period: Period
  inclusionRule: string
}
export interface Evidence {
  attemptId: string
  missionTitle?: string
  kind?: 'ANSWER' | 'REFLECTION'
  answerId: string | null
  answerVersion?: number | null
  submittedAt?: string
  quote?: string
  available: boolean
}
export interface MessageResult {
  messageId: string
  answer: string
  scope: Scope
  metrics: Metric[]
  evidence: Evidence[]
  recordCount: number
  source: 'LLM' | 'LLM_RETRY' | 'TEMPLATE'
  fallback?: AnalysisFallback | null
  notice?: AnalysisNotice | null
  verification: AnalysisVerification
}
export interface ConversationMessage extends Partial<MessageResult> {
  correctionNotice?: boolean
  messageId: string
  question: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  failureCode?: string
  retryable?: boolean
}
export interface Conversation {
  conversationId: string
  childId: string
  /** 일일 리포트 고정 대화(P25)면 그 리포트와 판 */
  reportId?: string
  reportRevision?: number
  period: Period
  title: string
  createdAt: string
  messages: ConversationMessage[]
}
export interface Clarification {
  question: string
  options: { label: string; scope: Scope }[]
}
export interface StreamState {
  phase: 'IDLE' | 'RUNNING' | 'CLARIFICATION' | 'DONE' | 'FAILED'
  temporary: string
  messageId?: string
  message?: string
  clarification?: Clarification
  result?: MessageResult
}
/** 리포트 기간 종류(P24, API 명세 2.5 구현 예정). 서버가 아직 주지 않으면 주간으로 본다. */
export type ReportPeriodType = 'DAILY' | 'WEEKLY'
export const reportPeriodType = (r: { periodType?: ReportPeriodType }) => r.periodType ?? 'WEEKLY'
/**
 * 일일 리포트의 문제별 항목(API 명세 2.5 `problems[]`, 구현 예정).
 * report #390 구현 때 세부 필드가 바뀌면 여기만 맞춘다. 서술 없이 실제 기록만 담는다(P24).
 */
export interface DailyProblem {
  missionId: string
  attemptId?: string
  title: string
  context: 'THEME_DAY' | 'THEME_REVIEW' | 'EXTRA' | null
  judgment: 'CORRECT' | 'PARTIAL' | 'RETHINK' | 'HELD' | null
  followups: { question: string; answer: string | null }[]
  finalAnswer: string | null
  elements: { label: string; satisfied: boolean }[]
  reflection: { difficulty: string | null; text: string | null; written: boolean } | null
  quotes: { answerId: string; text: string; verified: boolean }[]
}
/** 주간 리포트의 주간 테마 요약(FN-RPT-17, 구현 예정). */
export interface ThemeSummary {
  state?: QueryState
  themeId: string | null
  title: string | null
  days: { day: string; missionId: string; title?: string; completed: boolean }[]
  completed: boolean
  reviewRetries: { missionId: string; title?: string }[]
}
export interface ReportItem {
  reportId: string
  childId: string
  periodType?: ReportPeriodType
  period: Period
  revision: number
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  state: QueryState
  generatedAt?: string | null
}
export interface WeeklyReport extends ReportItem {
  parentSharingEnabled?: boolean
  correctionNotice?: boolean
  /** 일일 리포트만(DAILY) */
  problems?: DailyProblem[]
  /** 주간 리포트의 테마 요약(없으면 생략) */
  themeSummary?: ThemeSummary | null
  revisions: { revision: number; generatedAt?: string }[]
  inclusionRule: string
  metrics: (Metric & { itemId?: string })[]
  thinkingTypes: ThinkingActivity[]
  changes: {
    itemId?: string
    attemptId: string
    followup: string | null
    first: { answerId?: string; text: string | null }
    revised: { answerId?: string; text: string | null }
    counts: { chars: number[]; sentences: number[]; reasonConnectives: number[] }
  }[]
  reflections: {
    attemptId: string
    difficulty: string | null
    text: string | null
    written: boolean
    itemId?: string
  }[]
  quotes: {
    attemptId: string
    answerId: string
    text: string
    verified: boolean
    itemId?: string
  }[]
  eveningQuestion?: string
  narrative: { text: string; source: string; modelExplanation?: string | null } | null
  verification: { numbersMatched: boolean; quotesMatched: boolean }
  generatedAt?: string
  versions?: Record<string, string | null>
}
export function validPeriod(p: Period) {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(p.from) &&
    /^\d{4}-\d{2}-\d{2}$/.test(p.to) &&
    !Number.isNaN(Date.parse(p.from)) &&
    !Number.isNaN(Date.parse(p.to)) &&
    new Date(p.from).toISOString().slice(0, 10) === p.from &&
    new Date(p.to).toISOString().slice(0, 10) === p.to &&
    p.from <= p.to
  )
}
export function metricText(m: Metric) {
  if (typeof m.count !== 'number' || !Number.isFinite(m.count)) return '확인되지 않음'
  if (m.value !== null && (typeof m.value !== 'number' || !Number.isFinite(m.value)))
    return '확인되지 않음'
  return m.value === null ? `${m.count}건` : `${Math.round(m.value * 100)}% · ${m.count}건`
}
// 자체 목업의 고정 연결어 목록. 실제 집계/목록은 서버 정책을 따른다.
export function changeCounts(text: string) {
  return {
    chars: text.length,
    sentences: text.split(/[.?!\n]+/).filter((s) => s.trim()).length,
    reasonConnectives: ['왜냐하면', '때문', '그래서', '따라서'].reduce(
      (n, s) => n + text.split(s).length - 1,
      0,
    ),
  }
}
export function reduceAnalysis(
  s: StreamState,
  event: { event: string; data: unknown },
): StreamState {
  const data = event.data as Record<string, unknown>
  if (event.event === 'status')
    return {
      ...s,
      phase: 'RUNNING',
      message: String(data.message ?? '기록을 조회하고 있습니다.'),
      messageId: typeof data.messageId === 'string' ? data.messageId : s.messageId,
    }
  if (event.event === 'delta')
    return { ...s, phase: 'RUNNING', temporary: s.temporary + String(data.text ?? '') }
  if (event.event === 'clarification')
    return {
      ...s,
      phase: 'CLARIFICATION',
      temporary: '',
      clarification: data as unknown as Clarification,
    }
  if (event.event === 'error') return { ...s, phase: 'FAILED', temporary: '', result: undefined }
  if (event.event === 'result') {
    const r = data as unknown as MessageResult
    if (!r.scope) throw new Error('답변 범위가 없습니다.')
    assertVerifiedAnalysis(r)
    return {
      ...s,
      phase: 'DONE',
      temporary: '',
      clarification: undefined,
      result: r,
      messageId: r.messageId,
    }
  }
  return s
}

export function assertVerifiedAnalysis(r: Pick<MessageResult, 'source' | 'verification' | 'fallback' | 'notice'>): void {
  const fail = () => { throw new Error('숫자·인용·표현 대조 또는 응답 출처 계약이 올바르지 않습니다.') }
  if (r.verification?.numbersMatched !== true || r.verification.quotesMatched !== true || r.verification.contentAllowed !== true) fail()
  if (!['LLM', 'LLM_RETRY', 'TEMPLATE'].includes(r.source)) fail()
  if (r.source === 'TEMPLATE' ? Boolean(r.fallback) === Boolean(r.notice) : Boolean(r.fallback || r.notice)) fail()
  if (r.fallback) {
    const draft = r.fallback.draftVerification
    if (r.fallback.reason === 'VERIFICATION_FAILED') {
      if (!draft || [draft.numbersMatched, draft.quotesMatched, draft.contentAllowed].some(v => typeof v !== 'boolean') ||
        [draft.numbersMatched, draft.quotesMatched, draft.contentAllowed].every(v => v === true)) fail()
    } else if (r.fallback.reason !== 'AI_UNAVAILABLE' || draft !== null) fail()
  }
  if (r.notice && !['NO_RECORD', 'NO_CHANGES', 'NO_REFLECTIONS', 'UNSUPPORTED', 'MATH_CHECK'].includes(r.notice.reason)) fail()
}
export function analysisResultLabel(r: { source?: string; fallback?: AnalysisFallback | null; notice?: AnalysisNotice | null }): string {
  if (r.notice) return {
    NO_RECORD: '기록 없음 안내', NO_CHANGES: '비교할 보완 답변 없음', NO_REFLECTIONS: '돌아보기 없음',
    UNSUPPORTED: '제공 범위 안내', MATH_CHECK: '수학 점검 제공 범위 안내',
  }[r.notice.reason]
  if (r.fallback?.reason === 'AI_UNAVAILABLE') return 'AI 응답 불가 · 확인된 기록으로 만든 규칙 응답'
  if (r.fallback?.reason === 'VERIFICATION_FAILED') return 'AI 초안 대조 실패 · 확인된 기록으로 만든 규칙 응답'
  return r.source === 'TEMPLATE' ? '확인된 기록으로 만든 규칙 응답' : '숫자·인용 대조 완료'
}
