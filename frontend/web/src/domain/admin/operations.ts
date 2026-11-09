import type { Mission, Period, ThinkingType, InputType, PublicAttempt } from '../classroom.ts'
import type { AchievementStandard } from './missionStandards.ts'
import { allowsLevel, covers, elementCodesFit, isAnswerCode, isLevelShape, isValidElementCode } from './missionStandards.ts'
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
  detail?: Record<string, unknown> | null
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
  /** 성취기준별 성취수준 단계 {코드: A~E} (#353). 고르지 않으면 null 또는 빠짐 */
  achievementLevels?: Record<string, string> | null
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
    /** 요소가 기대는 성취기준 코드 (FN 1.5). 미션 성취기준 중 하나, 정답 요소는 null */
    standardCode?: string | null
  }[]
  answerKey?: AnswerKey | null
  exampleAnswer?: string | null
  forbiddenTerms: string[]
  hints: string[]
  /** #69 서술 M2 핵심어 묶음. 관리자 화면은 편집하지 않고 저장 때 기존 값을 그대로 다시 보낸다(#306). */
  keywords?: string[]
  /** #69 논술 M2 글 종류. keywords와 같이 보존만 한다. */
  essayType?: EssayType | null
}
/** learning-service.yaml `AdminRubric.essayType` */
export const essayTypes = ['설명글', '글짓기', '주장', '찬성반대', '대안제시'] as const
export type EssayType = (typeof essayTypes)[number]
export interface AdminMission {
  missionId: string
  code?: string
  /** 처음 만들어진 방식 (#353): 사람 작성 또는 LLM 초안 채택 */
  source?: 'MANUAL' | 'LLM_DRAFT'
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
  limitations?: string[]
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
  corrections: { reason: string; corrected: string; createdAt: string; impact: string | Record<string, string | string[]> | null }[]
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
    AFFECTED: '영향 있음(정정 안내 표시)',
    NOT_AFFECTED: '영향 없음',
  }
  if (areas.some(([key]) => !Object.hasOwn(states, String(impact[key]))))
    return '반영 정보의 형식을 확인할 수 없습니다.'
  // 대화·리포트는 판정이 쓰였는지(영향), 집계는 정정을 반영했는지로 구분한다 (#244).
  const text = (key: string) =>
    key !== 'aggregation' && impact[key] === 'UNKNOWN' ? '영향 여부 미확인' : states[String(impact[key])]
  return areas.map(([key, label]) => `${label}: ${text(key)}`).join(' / ')
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
  achievementStandards: '성취기준 (표에 있는 코드, 미션 학년이 성취기준 학년군 안)',
  achievementLevels: '성취수준 (고른 성취기준의 단계, 초 A~C·중 A~E)',
  choices: '선택 항목', categories: '분류 그룹',
  rubric: '기준표 버전', 'rubric.elements': '기준표 요소 (풀이 단계는 최종 답 외 요소 포함)',
  'rubric.elements.points': '요소 이름·양의 배점',
  'rubric.elements.code': '요소 code (생각 유형·입력 방식에 맞는 요소, 고르기·순서·분류는 정답 요소 하나)',
  'rubric.elements.standardCode': '요소 연결 성취기준 (미션 성취기준 중 하나, 정답 요소는 비움)',
  answerKey: '정답 키',
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
/**
 * 게시 전 확인 (learning PublishSnapshot.missingFields와 같은 코드·순서).
 * standards는 미션 성취기준 코드로 찾은 표 행이며, 없으면(조회 전·실패) 표·학년군·단계 수 검사는 건너뜀
 */
export function missingMissionFields(m: AdminMission, standards?: Record<string, AchievementStandard>): string[] {
  const v = m.versions.find((v) => v.version === m.currentVersion),
    r = m.rubrics.find((r) => r.version === m.currentRubricVersion), missing: string[] = []
  if (!v?.title.trim()) missing.push('title')
  if (!v?.question.trim()) missing.push('question')
  if (!v?.subject.trim()) missing.push('subject')
  if (!v || !Number.isInteger(v.gradeMin) || !Number.isInteger(v.gradeMax) || v.gradeMin < 3 ||
      v.gradeMax > 6 || v.gradeMin > v.gradeMax || (v.inputType === 'ESSAY' && v.gradeMin < 5)) missing.push('grade')
  const codes = v?.achievementStandards ?? []
  if (!codes.length || codes.some((s) => !s.trim()) ||
      (standards && codes.some((c) => !standards[c] || !covers(standards[c], v!.gradeMin, v!.gradeMax)))) missing.push('achievementStandards')
  if (Object.entries(v?.achievementLevels ?? {}).some(([code, level]) => !codes.includes(code) ||
      (standards ? !standards[code] || !allowsLevel(standards[code], level) : !isLevelShape(level)))) missing.push('achievementLevels')
  if (v && ['CHOICE', 'ORDERING', 'CLASSIFICATION'].includes(v.inputType) && !v.choices?.length) missing.push('choices')
  if (v?.inputType === 'CLASSIFICATION' && !v.categories?.length) missing.push('categories')
  if (!r) missing.push('rubric')
  if (r && (!r.elements.length ||
      (v?.inputType === 'SOLUTION_STEPS' && !r.elements.some((e) => e.code !== 'FINAL_ANSWER')) ||
      (v?.inputType !== 'SOLUTION_STEPS' && r.elements.some((e) => e.code === 'FINAL_ANSWER')))) missing.push('rubric.elements')
  if (r?.elements.some((e) => !e.label.trim() || !Number.isInteger(e.points) || e.points <= 0)) missing.push('rubric.elements.points')
  if (v && r?.elements.length && !elementCodesFit(r.elements.map((e) => e.code), v.thinkingType, v.inputType)) missing.push('rubric.elements.code')
  if (r?.elements.some((e) => e.standardCode != null && (isAnswerCode(e.code) || !codes.includes(e.standardCode)))) missing.push('rubric.elements.standardCode')
  if (v && r && !['NARRATIVE', 'ESSAY'].includes(v.inputType) && !validAnswerKey(v, r.answerKey)) missing.push('answerKey')
  if (v && r && ['NARRATIVE', 'ESSAY'].includes(v.inputType) && !r.exampleAnswer?.trim()) missing.push('exampleAnswer')
  if (m.reviews.filter((x) => x.missionVersion === m.currentVersion && x.rubricVersion === m.currentRubricVersion)
      .at(-1)?.result !== 'APPROVED') missing.push('review')
  return missing
}
/** 기준표 저장 전 확인 (learning AdminMissionController 400 규칙: core가 detail을 지워 보내므로 화면에서 먼저 알림) */
export function rubricSaveErrors(elements: Rubric['elements']): string[] {
  const errors: string[] = []
  elements.forEach((e, i) => {
    if (!e.code.trim()) errors.push(`요소 ${i + 1}: code를 고르세요.`)
    else if (!isValidElementCode(e.code)) errors.push(`요소 ${i + 1}: code ${e.code}는 표준 요소·e+숫자(e1, e2…)·정답 코드가 아닙니다. 요소 종류를 다시 고르세요.`)
    if (!e.label.trim()) errors.push(`요소 ${i + 1}: 이름을 입력하세요.`)
    if (!Number.isInteger(e.points) || e.points < 1) errors.push(`요소 ${i + 1}: 배점은 1 이상 정수여야 합니다.`)
    if (e.standardCode != null && !e.standardCode.trim()) errors.push(`요소 ${i + 1}: 연결 성취기준이 비어 있습니다.`)
  })
  const codes = elements.map((e) => e.code)
  const dup = codes.filter((c, i) => c && codes.indexOf(c) !== i)
  if (dup.length) errors.push(`같은 code를 두 요소에 쓸 수 없습니다: ${[...new Set(dup)].join(', ')}`)
  return errors
}
