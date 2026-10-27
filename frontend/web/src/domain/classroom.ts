export type Role = 'PARENT' | 'STUDENT' | 'ADMIN'
export interface Child {
  id: string
  nickname: string
  grade: number
  birthYear: number
  plan: 'FREE' | 'PREMIUM'
  /** 학부모 화면 전용 PIN 상태 (API 명세 2.1 `/children`, #59). 학생 응답에는 없다. */
  pinSet?: boolean
  pinLocked?: boolean
}
export interface Session {
  nextAction?: 'CONSENT_REQUIRED' | 'CHILD_REGISTRATION_REQUIRED' | 'READY'
  startPath?: string
  role: Role
  /** 학생 진입 경로. DEVICE는 등록 기기 + PIN(refresh 없음, 만료 시 PIN 재입력), GUARDIAN은 학부모 동석. */
  entry?: 'DEVICE' | 'GUARDIAN'
  child?: Child
  permissions?: import('./admin/operations.ts').Permission[]
}
export type InputType =
  'NARRATIVE' | 'SOLUTION_STEPS' | 'ESSAY' | 'CHOICE' | 'ORDERING' | 'CLASSIFICATION'
export type ThinkingType = 'ANALYZE' | 'EVALUATE' | 'CREATE' | 'SOLVE' | 'REFLECT'
export interface Mission {
  id: string
  title: string
  subject: string
  grade: number
  thinkingType: ThinkingType
  gradeMax?: number
  inputType: InputType
  question: string
  hint: string
  scene: 'math' | 'science' | 'english' | 'korean'
  sceneUri?: string
  staticSceneUri?: string
  choices?: { id: string; label: string }[]
  categories?: { id: string; label: string }[]
  status?: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED'
  attemptId?: string
  position?: number
  total?: number
}
export interface AnswerContent {
  inputType: InputType
  text: string
  finalAnswer: string
  steps: string[]
  essay: { claim: string; reasons: [string, string]; rebuttal: string }
  choiceIds: string[]
  assignments: { choiceId: string; categoryId: string }[]
  dictatedByGuardian: boolean
}
export interface Draft {
  answer: AnswerContent
  memo: string
  version: string
  savedAt?: string
}
export type ProcessStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED'
export type JudgmentResult = 'CORRECT' | 'PARTIAL' | 'RETHINK' | 'HELD'
export type NextAction = 'ANSWER_FOLLOWUP' | 'FINISH'
export interface FeedbackElement {
  elementId: string
  label: string
  satisfied: boolean
  quote: string | null
  sourceType: 'RULE' | 'ANSWER_KEY' | 'AI_OBSERVATION'
}
export const isVerifiedElement = (element: FeedbackElement, texts: string[]) =>
  element.satisfied && !!element.quote && texts.some((text) => text.includes(element.quote!))
export interface Feedback {
  status: ProcessStatus
  judgment?: {
    result: JudgmentResult
    trial: boolean
    heldReason?: string
    elements?: FeedbackElement[]
  }
  followup?: {
    followupId: string
    type: 'ONE_STEP_MORE' | 'TELL_MORE' | 'LOOK_AGAIN'
    question: string
    source: 'LLM' | 'LLM_RETRY' | 'BANK'
  }
  nextActions: NextAction[]
}
export interface Answer {
  answerId: string
  version: number
  submittedAt: string
  inputType: InputType
  text: string
  followupId?: string
  feedback: Feedback
  content?: AnswerContent
}
export interface Reflection {
  difficulty: '쉬웠어' | '보통' | '어려웠어'
  text: string
}
export interface Attempt {
  attemptId: string
  studentId: string
  mission: Mission
  status: 'IN_PROGRESS' | 'COMPLETED'
  finishedAt?: string
  answers: Answer[]
  reflection?: Reflection
  draft?: Draft
  helped: boolean
  reveal?: string
  revealKind?: 'ANSWER' | 'EXAMPLE'
  checklist?: FeedbackElement[]
}
export interface StudentHome {
  student: Child
  state: import('./queryState.ts').QueryState
  period: Period
  resume: Attempt | null
  missions: Mission[]
}
export type PublicAttempt = Omit<Attempt, 'draft'>
export interface Period {
  from: string
  to: string
}
export interface Metric {
  label: string
  count: number
  numerator: number
  denominator: number
  formula: string
  value: number | null
  period: Period
  sourceType: 'RECORD' | 'RULE' | 'ANSWER_KEY' | 'AI_OBSERVATION'
  state: 'OK' | 'NO_RECORD' | 'INSUFFICIENT_SAMPLE'
}
export interface Report {
  reportId: string
  childId: string
  period: Period
  revision: number
  revisions: number[]
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  state: 'OK' | 'NO_RECORD' | 'INSUFFICIENT_SAMPLE'
  metrics: Metric[]
  records: PublicAttempt[]
  narrative: string | null
  eveningQuestion?: string
  regenerations: number
}
export interface AnalysisResult {
  source: 'LLM' | 'TEMPLATE'
  answer: string
  evidence: { attemptId: string; answerId: string; quote: string; available: boolean }[]
  verification: { numbersMatched: boolean; quotesMatched: boolean }
  fallback?: { reason: string }
}
export type DemoScenario =
  | 'normal'
  | 'draft-fail'
  | 'draft-conflict'
  | 'submit-fail'
  | 'ai-fail'
  | 'held'
  | 'bank'
  | 'report-fail'
  | 'correct'
  | 'partial'
  | 'rethink'
  | 'running'
  | 'finish-unmet'
  | 'home-empty'
  | 'home-fail'
  | 'home-processing'
  | 'home-small'
  | 'input-fixtures'
  | 'token-expired'
  | 'refresh-fail'
export const thinkingLabels: Record<ThinkingType, string> = {
  ANALYZE: '분석하기',
  EVALUATE: '따져 보기',
  CREATE: '새로 만들기',
  SOLVE: '문제 해결하기',
  REFLECT: '돌아보기',
}
export const inputLabels: Record<InputType, string> = {
  NARRATIVE: '글쓰기',
  SOLUTION_STEPS: '풀이 단계',
  ESSAY: '주장과 까닭',
  CHOICE: '고르기',
  ORDERING: '순서 맞추기',
  CLASSIFICATION: '분류하기',
}
export function blankAnswer(inputType: InputType): AnswerContent {
  return {
    inputType,
    text: '',
    finalAnswer: '',
    steps: ['', ''],
    essay: { claim: '', reasons: ['', ''], rebuttal: '' },
    choiceIds: [],
    assignments: [],
    dictatedByGuardian: false,
  }
}
export function answerText(a: AnswerContent): string {
  if (a.inputType === 'SOLUTION_STEPS')
    return [
      `답: ${a.finalAnswer}`,
      ...a.steps.filter(Boolean).map((s, i) => `${i + 1}. ${s}`),
    ].join('\n')
  if (a.inputType === 'ESSAY')
    return [a.essay.claim, ...a.essay.reasons, a.essay.rebuttal].filter(Boolean).join('\n')
  if (a.inputType === 'CLASSIFICATION')
    return a.assignments.map((v) => `${v.choiceId}: ${v.categoryId}`).join('\n')
  return a.inputType === 'CHOICE' || a.inputType === 'ORDERING'
    ? [a.choiceIds.join(', '), a.text].filter(Boolean).join('\n')
    : a.text
}
export function validateAnswer(a: AnswerContent, mission: Mission): string | null {
  if (a.inputType !== mission.inputType) return '미션에서 정한 답변 방식으로 작성해 주세요.'
  if (a.inputType === 'ESSAY' && mission.grade < 5)
    return '논술 틀은 초등 5~6학년에서 사용할 수 있어요.'
  if (
    a.inputType === 'ESSAY' &&
    (a.essay.reasons.length !== 2 ||
      ![a.essay.claim, ...a.essay.reasons, a.essay.rebuttal].every((v) => v.trim()))
  )
    return '주장, 까닭 두 가지, 다른 의견에 대한 답을 채워 주세요.'
  if (a.inputType === 'SOLUTION_STEPS' && (!a.finalAnswer.trim() || !a.steps.some((s) => s.trim())))
    return '답과 풀이 과정을 함께 남겨 주세요.'
  if (a.inputType === 'NARRATIVE' && !a.text.trim()) return '내 생각을 먼저 적어 주세요.'
  if (
    a.inputType === 'CHOICE' &&
    (a.choiceIds.length !== 1 || !mission.choices?.some((c) => c.id === a.choiceIds[0]))
  )
    return '답을 하나 골라 주세요.'
  if (
    a.inputType === 'CLASSIFICATION' &&
    (a.assignments.length !== mission.choices?.length ||
      new Set(a.assignments.map((v) => v.choiceId)).size !== a.assignments.length ||
      a.assignments.some(
        (v) =>
          !mission.choices?.some((c) => c.id === v.choiceId) ||
          !mission.categories?.some((c) => c.id === v.categoryId),
      ))
  )
    return '모든 항목을 알맞은 그룹에 한 번씩 넣어 주세요.'
  if (
    a.inputType === 'ORDERING' &&
    (a.choiceIds.length !== mission.choices?.length ||
      new Set(a.choiceIds).size !== a.choiceIds.length ||
      a.choiceIds.some((id) => !mission.choices?.some((c) => c.id === id)))
  )
    return '모든 항목의 순서를 정해 주세요.'
  return null
}
export function latestFeedback(a: PublicAttempt): Feedback | undefined {
  return a.answers.at(-1)?.feedback
}
export function canFinish(a: PublicAttempt): boolean {
  return (
    a.status === 'IN_PROGRESS' &&
    !a.finishedAt &&
    a.answers.some((v) => v.feedback.status === 'DONE') &&
    !!latestFeedback(a)?.nextActions.includes('FINISH')
  )
}
export function canAddAnswer(a: PublicAttempt): boolean {
  return (
    a.status === 'IN_PROGRESS' &&
    !a.finishedAt &&
    a.answers.length < 3 &&
    (a.answers.length === 0 || !!latestFeedback(a)?.nextActions.includes('ANSWER_FOLLOWUP'))
  )
}
export function publicAttempt(a: Attempt): PublicAttempt {
  return structuredClone({
    attemptId: a.attemptId,
    studentId: a.studentId,
    mission: a.mission,
    status: a.status,
    finishedAt: a.finishedAt,
    answers: a.answers,
    reflection: a.reflection,
    helped: a.helped,
    reveal: a.reveal,
    revealKind: a.revealKind,
    checklist: a.checklist,
  })
}
export function inPeriod(iso: string, p: Period): boolean {
  const date = new Date(iso)
  if (!Number.isFinite(date.getTime())) return false
  const day = new Date(date.getTime() + 9 * 3600000).toISOString().slice(0, 10)
  return day >= p.from && day <= p.to
}
export function eligibleRecords(records: PublicAttempt[], period: Period): PublicAttempt[] {
  return records.filter(
    (r) =>
      r.answers.some((a) => inPeriod(a.submittedAt, period)) &&
      !r.answers.every((a) => a.feedback.status === 'FAILED'),
  )
}
export const demoToday = '2026-10-26'
export const recentPeriod: Period = { from: '2026-10-20', to: demoToday }
export const previousWeek: Period = { from: '2026-10-19', to: '2026-10-25' }
export const thisWeek: Period = { from: demoToday, to: '2026-11-01' }
/** 실제 API 조회 기간은 한국 시간 기준. 시연의 고정 날짜와 분리한다. */
export function calendarPeriods(now = new Date()) {
  const day = new Date(
    new Date(now.getTime() + 9 * 3600000).toISOString().slice(0, 10) + 'T00:00:00Z',
  )
  const date = (offset: number) =>
    new Date(day.getTime() + offset * 86400000).toISOString().slice(0, 10)
  const monday = -((day.getUTCDay() + 6) % 7)
  return {
    recentPeriod: { from: date(-6), to: date(0) },
    previousWeek: { from: date(monday - 7), to: date(monday - 1) },
    thisWeek: { from: date(monday), to: date(monday + 6) },
    olderWeek: { from: date(monday - 14), to: date(monday - 8) },
  }
}
export function shortRange(period: Period) {
  return `${period.from.slice(5).replace('-', '.')}~${period.to.slice(5).replace('-', '.')}`
}
export function counts(records: PublicAttempt[], period: Period): Metric[] {
  const rows = eligibleRecords(records, period),
    n = rows.length
  const extra = rows.filter(
    (r) => r.answers.filter((a) => inPeriod(a.submittedAt, period)).length > 1,
  ).length
  const state = n === 0 ? 'NO_RECORD' : n < 5 ? 'INSUFFICIENT_SAMPLE' : 'OK'
  return [
    {
      label: '답을 남긴 활동',
      count: n,
      numerator: n,
      denominator: n,
      formula: '기간 내 제출 답변이 있는 시도 수 (미완료 포함, 실패만 있는 시도 제외)',
      value: null,
      period,
      sourceType: 'RECORD',
      state,
    },
    {
      label: '생각을 덧붙인 활동',
      count: extra,
      numerator: extra,
      denominator: n,
      formula: '기간 내 보완 답변이 있는 시도 / 집계 대상 시도',
      value: n >= 5 ? extra / n : null,
      period,
      sourceType: 'RECORD',
      state,
    },
  ]
}
