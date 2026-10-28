import type { Mission, Period, ThinkingType, InputType, PublicAttempt } from '../classroom.ts'
import type { QueryState } from '../queryState.ts'
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
  updatedAt: string
  executions: {
    executionId: string
    attemptNo: number
    status: JobStatus
    errorCode: string | null
    errorDetail: string | null
    triggeredBy: string | null
    startedAt: string
    finishedAt: string | null
  }[]
}
export interface Overview {
  period: Period
  state: QueryState
  inclusionRule: string
  attempts: number
  completed: number
  jobCounts: { type: JobType; status: JobStatus; count: number }[]
  missionCounts: { status: MissionStatus; count: number }[]
}
export interface Audit {
  id: string
  actorUserId: string
  action: string
  targetType: string
  targetId: string
  result: 'SUCCESS' | 'FAILURE'
  detail: string
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
  guide: string
  scene: Mission['scene']
  sceneUri: string
  staticSceneUri: string
  achievementStandards: string[]
  choices?: Mission['choices']
  categories?: Mission['categories']
  createdAt: string
}
export interface Rubric {
  version: number
  elements: {
    code: string
    label: string
    description: string
    points: number
    commonErrors: string[]
    goodThought: boolean
    judgeVerified: boolean
  }[]
  answerKey?: string
  exampleAnswer?: string
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
  versions: MissionVersion[]
  rubrics: Rubric[]
  reviews: {
    missionVersion: number
    rubricVersion: number
    result: 'APPROVED' | 'CHANGES_REQUESTED'
    comment: string
    createdAt: string
  }[]
}
export interface ModelVersion {
  id: string
  kind: 'RUBRIC' | 'MODEL' | 'PROMPT' | 'GENERATION'
  name: string
  version: string
  status: 'REGISTERED' | 'ACTIVE' | 'INACTIVE'
  evalResult?: string
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
export function missingMissionFields(m: AdminMission): string[] {
  const v = m.versions.find((v) => v.version === m.currentVersion),
    r = m.rubrics.find((r) => r.version === m.currentRubricVersion),
    missing: string[] = []
  if (!v?.title.trim()) missing.push('제목')
  if (!v?.question.trim()) missing.push('질문')
  if (!v?.subject.trim()) missing.push('교과')
  if (!v || v.gradeMin < 3 || v.gradeMax > 6 || v.gradeMin > v.gradeMax)
    missing.push('지원 학년 3~6')
  if (v?.inputType === 'ESSAY' && v.gradeMin < 5) missing.push('논술 학년 5~6')
  if (!v?.achievementStandards.some((s) => s.trim())) missing.push('성취기준')
  if (!r) missing.push('기준표 버전')
  if (v && ['CHOICE', 'ORDERING', 'CLASSIFICATION'].includes(v.inputType) && !v.choices?.length)
    missing.push('선택 항목')
  if (v?.inputType === 'CLASSIFICATION' && !v.categories?.length) missing.push('분류 그룹')
  if (v && ['NARRATIVE', 'ESSAY'].includes(v.inputType) && !r?.elements.length)
    missing.push('기준표 요소')
  if (v && !['NARRATIVE', 'ESSAY'].includes(v.inputType) && !r?.answerKey?.trim())
    missing.push('정답 키')
  if (v && ['NARRATIVE', 'ESSAY'].includes(v.inputType) && !r?.exampleAnswer?.trim())
    missing.push('예시 답')
  if (r?.elements.some((e) => !e.label.trim() || e.points <= 0)) missing.push('요소 이름·양의 배점')
  if (
    m.reviews
      .filter(
        (x) => x.missionVersion === m.currentVersion && x.rubricVersion === m.currentRubricVersion,
      )
      .at(-1)?.result !== 'APPROVED'
  )
    missing.push('현재 버전 검토 승인')
  return missing
}
