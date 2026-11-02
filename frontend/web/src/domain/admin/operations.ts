import type { Mission, Period, ThinkingType, InputType, PublicAttempt } from '../classroom.ts'
export type Permission = 'CONTENT' | 'PAYMENT_VIEW' | 'PAYMENT_REFUND' | 'SERVICE_OPS'
export type JobStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
export type JobType = 'CONVERSATION' | 'REPORT' | 'NOTIFICATION'
export type MissionStatus = 'DRAFT' | 'REVIEW_REQUIRED' | 'PUBLISHED' | 'UNPUBLISHED'
export interface Job {
  jobId: string
  type: JobType
  status: JobStatus
  retryCount: number
  failureReason: string | null
  createdAt: string
  retryable: boolean
  retryUnavailableReason: string | null
  executions: {
    executionId: string
    attemptNo: number
    status: JobStatus
    errorCode: string | null
    triggeredBy: string | null
    startedAt: string
    finishedAt: string | null
  }[]
}
export type JobRetryResult = Job | {
  jobId: string
  type: 'REPORT'
  originalJobId: string
  status: 'QUEUED'
  acceptedAt: string
} | {
  jobId: string
  type: 'CONVERSATION'
  retryRequestId: string
  generation: number
  status: 'QUEUED'
  acceptedAt: string
}
export function jobRetryMessage(status: JobStatus): string {
  return {
    QUEUED: '재처리를 접수했습니다. 작업 상태를 조회해 결과를 확인해 주세요.',
    RUNNING: '재처리 중입니다. 아직 완료되지 않았습니다.',
    COMPLETED: '서버에서 재처리 완료를 확인했습니다.',
    FAILED: '재처리 실패 · 완료로 표시하지 않습니다.',
  }[status]
}
export interface OperationQueue {
  name: string
  kind: 'WORK' | 'RETRY' | 'DLQ'
  messages: number
  messagesReady: number
  messagesUnacknowledged: number
  consumers: number
  state: string
}
export interface Overview {
  period: Period
  inclusionRule: string
  learning: { attempts: number; completedAttempts: number; students: number; inclusionRule: string }
  jobCounts: { type: JobType; status: JobStatus; count: number }[]
}
export interface Audit {
  id: string
  actorUserId: string
  action: string
  targetType: string
  targetId: string | null
  result: 'SUCCESS' | 'FAILURE'
  createdAt: string
}
export interface MissionVersion {
  version: number
  title: string
  subject: string
  gradeMin: number
  gradeMax: number
  thinkingType: ThinkingType
  inputType: InputType
  question: string
  guide: string | null
  answerUnit?: string | null
  inputTemplate?: string[]
  sceneUri: string | null
  staticSceneUri: string | null
  achievementStandards: string[]
  choices?: Mission['choices']
  categories?: Mission['categories']
  createdAt: string
}
/** Kotlin AnswerKey의 사용하지 않는 필드는 응답에서 null일 수 있습니다. */
export interface AnswerKey {
  choiceIds?: string[] | null
  assignments?: { choiceId: string; categoryId: string }[] | null
  finalAnswer?: string | null
}
export interface Rubric {
  version: number
  elements: {
    code: string
    label: string
    description: string | null
    points: number
    commonErrors: string[]
    goodThought: boolean
    judgeVerified: boolean
  }[]
  answerKey?: AnswerKey | null
  exampleAnswer?: string | null
  forbiddenTerms: string[]
  hints: string[]
}
export interface AdminMission {
  missionId: string
  status: MissionStatus
  demoOnly: boolean
  currentVersion: number
  currentRubricVersion: number | null
  publishedVersion: number | null
  publishedRubricVersion: number | null
  versions: MissionVersion[]
  rubrics: Rubric[]
  reviews: {
    missionVersion: number
    rubricVersion: number
    result: 'APPROVED' | 'CHANGES_REQUESTED'
    comment: string | null
    createdAt: string
  }[]
}
export interface EvaluationEvidence {
  datasetId: string; datasetVersion: string; baselineVersion: string; comparisonReport: string
  trainingEvaluationSeparation: string; quoteAccuracy: string; calculationAccuracy: string; humanReview: string
  evaluatedScopes: string[]
}
export interface EvaluationRecord {
  evidence: EvaluationEvidence
  approval: null | { scopes: string[]; reason: string; approvedBy: string; approvedAt: string }
  activeScopes: string[]
  revision: number
}
export interface ModelVersion {
  id: string
  kind: 'RUBRIC' | 'MODEL' | 'PROMPT' | 'GENERATION'
  name: string
  version: string
  status: 'REGISTERED' | 'ACTIVE' | 'INACTIVE'
  evalResult?: EvaluationRecord | null
  refId?: string | null
  approvedBy?: string
  artifactUri?: string
  activatedAt?: string
  createdAt: string
}
export interface ErrorReport {
  reportId: string
  status: 'RECEIVED' | 'IN_REVIEW' | 'RESOLVED'
  targetType: string
  targetId: string
  category: string
  comment: string
  reviewReason?: string
  linkedAttempt?: PublicAttempt
  corrections: { reason: string; corrected: string; createdAt: string; impact: string | Record<string, string> | null }[]
}
/** A successful judgment correction does not imply that derived outputs were updated. */
export function correctionImpactText(impact: ErrorReport['corrections'][number]['impact']): string {
  if (impact === null) return '파생 결과 반영 정보 없음'
  if (typeof impact === 'string') return `이전 형식의 반영 정보: ${impact}`
  const areas = [
    ['conversation', '분석 대화'],
    ['aggregation', '학습 수치 집계'],
    ['report', '리포트'],
  ] as const
  const states: Record<string, string> = {
    APPLIED: '반영 확인',
    NOT_APPLIED: '미반영 확인(변경 대상 없음 포함, 오류·후속 처리 필요 아님)',
    UNKNOWN: '반영 여부 미확인',
  }
  if (areas.some(([key]) => !Object.hasOwn(states, impact[key])))
    return '반영 정보의 형식을 확인할 수 없습니다.'
  return areas.map(([key, label]) => `${label}: ${states[impact[key]]}`).join(' / ')
}

export interface Usage {
  period: Period
  items: {
    callType: string
    calls: number
    failures: number
    latencyMs: number
    inputTokens: number | null
    outputTokens: number | null
    costUsd: number | null
    unpricedCalls: number
  }[]
}
export const hasPermission = (permissions: Permission[] | undefined, p: Permission) =>
  !!permissions?.includes(p)
export const jobLabels: Record<JobStatus, string> = {
  QUEUED: '대기',
  RUNNING: '처리 중',
  COMPLETED: '완료',
  FAILED: '실패',
}
export const missionLabels: Record<MissionStatus, string> = {
  DRAFT: '작성 중',
  REVIEW_REQUIRED: '검토 필요',
  PUBLISHED: '공개',
  UNPUBLISHED: '비공개',
}
/** core는 영문 missingFields 코드만 전달합니다. */
export const missingFieldLabels: Record<string, string> = {
  title: '제목', question: '질문', subject: '교과', grade: '지원 학년 (논술 5~6학년)',
  achievementStandards: '성취기준', choices: '선택 항목', categories: '분류 그룹',
  rubric: '기준표 버전', 'rubric.elements': '기준표 요소 (풀이 단계는 최종 답 외 요소 포함)',
  'rubric.elements.points': '요소 이름·양의 배점', answerKey: '정답 키',
  exampleAnswer: '예시 답', review: '현재 버전 검토 승인',
}
export function missingFieldLabel(code: string) {
  if (missingFieldLabels[code]) return missingFieldLabels[code]
  const indexed = code.replace(/\[\d+\]/g, '')
  return missingFieldLabels[indexed] ?? `확인이 필요한 항목: ${code}`
}
export function validAnswerKey(v: MissionVersion, key: Rubric['answerKey']): boolean {
  if (!key || typeof key !== 'object' || Array.isArray(key)) return false
  const ids = v.choices?.map((c) => c.id) ?? []
  if (v.inputType === 'CHOICE' || v.inputType === 'ORDERING') {
    if (!('choiceIds' in key) || !Array.isArray(key.choiceIds)) return false
    const chosen = key.choiceIds
    return chosen.length > 0 && new Set(chosen).size === chosen.length &&
      chosen.every((id) => ids.includes(id)) &&
      (v.inputType === 'CHOICE' ? chosen.length === 1 : chosen.length === ids.length)
  }
  if (v.inputType === 'CLASSIFICATION') {
    if (!Array.isArray(key.assignments)) return false
    const groups = v.categories?.map((g) => g.id) ?? []
    const assignments = key.assignments
    return ids.length > 0 && assignments.length === ids.length &&
      new Set(assignments.map((a) => a.choiceId)).size === ids.length &&
      assignments.every((a) => ids.includes(a.choiceId) && groups.includes(a.categoryId))
  }
  return v.inputType === 'SOLUTION_STEPS' && 'finalAnswer' in key &&
    typeof key.finalAnswer === 'string' && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(key.finalAnswer.trim())
}
export function missingMissionFields(m: AdminMission): string[] {
  const v = m.versions.find((v) => v.version === m.currentVersion),
    r = m.rubrics.find((r) => r.version === m.currentRubricVersion), missing: string[] = []
  if (!v?.title.trim()) missing.push('title')
  if (!v?.question.trim()) missing.push('question')
  if (!v?.subject.trim()) missing.push('subject')
  if (!v || !Number.isInteger(v.gradeMin) || !Number.isInteger(v.gradeMax) || v.gradeMin < 3 ||
      v.gradeMax > 6 || v.gradeMin > v.gradeMax || (v.inputType === 'ESSAY' && v.gradeMin < 5)) missing.push('grade')
  if (!v?.achievementStandards.some((s) => s.trim())) missing.push('achievementStandards')
  if (!r) missing.push('rubric')
  if (v && ['CHOICE', 'ORDERING', 'CLASSIFICATION'].includes(v.inputType) && !v.choices?.length) missing.push('choices')
  if (v?.inputType === 'CLASSIFICATION' && !v.categories?.length) missing.push('categories')
  if (r && (!r.elements.length ||
      (v?.inputType === 'SOLUTION_STEPS' && !r.elements.some((e) => e.code !== 'FINAL_ANSWER')) ||
      (v?.inputType !== 'SOLUTION_STEPS' && r.elements.some((e) => e.code === 'FINAL_ANSWER')))) missing.push('rubric.elements')
  if (v && r && !['NARRATIVE', 'ESSAY'].includes(v.inputType) && !validAnswerKey(v, r.answerKey)) missing.push('answerKey')
  if (v && r && ['NARRATIVE', 'ESSAY'].includes(v.inputType) && !r.exampleAnswer?.trim()) missing.push('exampleAnswer')
  if (r?.elements.some((e) => !e.label.trim() || !Number.isInteger(e.points) || e.points <= 0)) missing.push('rubric.elements.points')
  if (m.reviews.filter((x) => x.missionVersion === m.currentVersion && x.rubricVersion === m.currentRubricVersion)
      .at(-1)?.result !== 'APPROVED') missing.push('review')
  return missing
}
