import type {
  AdminMission,
  Audit,
  Job,
  ModelVersion,
  ErrorReport,
} from '../../../domain/admin/operations.ts'
export const stamp = () => new Date().toISOString()
export const jobs: Job[] = (['FAILED', 'RUNNING', 'QUEUED', 'COMPLETED'] as const).map(
  (status, i) => ({
    jobId: `job-${i + 1}`,
    type: i === 0 ? 'NOTIFICATION' : i % 2 ? 'CONVERSATION' : 'REPORT',
    status,
    retryCount: 0,
    failureReason: status === 'FAILED' ? 'AI 응답 시간 초과 (원문 미포함)' : null,
    createdAt: '2026-10-25T10:00:00+09:00',
    retryable: status === 'FAILED' && i === 0,
    retryUnavailableReason: status === 'FAILED' && i === 0 ? null : 'JOB_NOT_FAILED',
    executions: [
      {
        executionId: `execution-${i}`,
        attemptNo: 1,
        status,
        errorCode: status === 'FAILED' ? 'AI_UNAVAILABLE' : null,
        triggeredBy: null,
        startedAt: '2026-10-25T10:00:00+09:00',
        finishedAt:
          status === 'FAILED' || status === 'COMPLETED' ? '2026-10-25T10:01:00+09:00' : null,
      },
    ],
  }),
)
export const missions: AdminMission[] = [
  {
    missionId: 'content-1',
    status: 'DRAFT',
    demoOnly: true,
    currentVersion: 1,
    currentRubricVersion: 1,
    publishedVersion: null,
    versions: [
      {
        version: 1,
        title: '우리 반 작은 정원',
        subject: '과학',
        gradeMin: 3,
        gradeMax: 4,
        thinkingType: 'ANALYZE',
        inputType: 'NARRATIVE',
        question: '잎의 모양을 비교하고 다른 점을 설명해 주세요.',
        guide: '눈으로 확인한 것을 적어 주세요.',
        scene: 'science',
        sceneUri: '',
        staticSceneUri: '',
        achievementStandards: ['자체 시연 성취기준'],
        createdAt: stamp(),
      },
    ],
    rubrics: [
      {
        version: 1,
        elements: [
          {
            code: 'e1',
            label: '관찰한 차이',
            description: '잎의 특징을 원문으로 확인',
            points: 1,
            commonErrors: ['관찰 없이 추측만 적음'],
            goodThought: true,
            judgeVerified: false,
          },
        ],
        exampleAnswer: '한쪽 잎은 더 넓고 다른 쪽 잎은 길쭉합니다.',
        forbiddenTerms: ['예시 답'],
        hints: ['잎의 크기와 모양을 각각 살펴보세요.'],
      },
    ],
    reviews: [],
  },
]
export const audits: Audit[] = []
export function audit(
  action: string,
  targetType: string,
  targetId: string,
  result: 'SUCCESS' | 'FAILURE',
  _detail: string,
) {
  audits.unshift({
    id: crypto.randomUUID(),
    actorUserId: 'mock-admin',
    action,
    targetType,
    targetId,
    result,
    createdAt: stamp(),
  })
}
export const modelVersions: ModelVersion[] = [
  {
    id: 'prompt-1',
    kind: 'PROMPT',
    name: 'judge',
    version: 'mock-1',
    status: 'ACTIVE',
    evalResult: '개발용 고정 평가 예시 · 실제 성능 승인 아님',
    approvedBy: 'mock-reviewer',
    activatedAt: stamp(),
    createdAt: stamp(),
  },
  {
    id: 'prompt-2',
    kind: 'PROMPT',
    name: 'judge',
    version: 'mock-2',
    status: 'INACTIVE',
    evalResult: '개발용 비교 평가 예시 · 실제 성능 승인 아님',
    approvedBy: 'mock-reviewer',
    createdAt: stamp(),
  },
]
export const reportedAttemptIds = new Map([['error-1', 'demo-seoyun-math']])
export const errorReports: ErrorReport[] = [
  {
    reportId: 'error-1',
    status: 'RECEIVED',
    targetType: 'JUDGMENT',
    targetId: 'mock-judgment',
    category: 'WRONG_JUDGMENT',
    comment: '자체 시연 답변의 판정 근거를 확인해 주세요.',
    corrections: [],
  },
]
export const retryReceipts = new Map<string, { jobId: string; response: Job }>()
