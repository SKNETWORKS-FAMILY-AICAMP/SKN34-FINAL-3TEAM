import type { Metric, Period, PublicAttempt, ThinkingType } from './classroom.ts'
import type { QueryState } from './queryState.ts'
export interface Page<T> {
  items: T[]
  page: number
  size: number
  totalElements: number
}
export interface ConsentDocument {
  documentId: string
  kind: 'TERMS' | 'PRIVACY' | 'GUARDIAN'
  version: string
  title: string
  content: string
  required: boolean
}
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
  answerId: string
  answerVersion?: number
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
  fallback?: { reason: string }
  verification: { numbersMatched: boolean; quotesMatched: boolean }
}
export interface ConversationMessage extends Partial<MessageResult> {
  messageId: string
  question: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  failureCode?: string
  retryable?: boolean
}
export interface Conversation {
  conversationId: string
  childId: string
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
export interface ReportItem {
  reportId: string
  childId: string
  period: Period
  revision: number
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  state: QueryState
  generatedAt?: string | null
}
export interface WeeklyReport extends ReportItem {
  revisions: { revision: number; generatedAt?: string }[]
  inclusionRule: string
  metrics: (Metric & { itemId?: string })[]
  thinkingTypes: ThinkingActivity[]
  changes: {
    itemId?: string
    attemptId: string
    followup: string | null
    first: { answerId: string; text: string }
    revised: { answerId: string; text: string }
    counts: { chars: number[]; sentences: number[]; reasonConnectives: number[] }
  }[]
  reflections: {
    attemptId: string
    difficulty: string
    text: string
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
    if (!r.scope || !r.verification?.numbersMatched || !r.verification.quotesMatched)
      throw new Error('숫자·인용 대조가 완료되지 않은 결과입니다.')
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
