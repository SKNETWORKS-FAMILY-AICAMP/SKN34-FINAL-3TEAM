import type {
  AdminMission,
  Audit,
  Job,
  ModelVersion,
  ErrorReport,
} from '../../../domain/admin/operations.ts'
import type { AchievementStandard, MissionDraft } from '../../../domain/admin/missionStandards.ts'
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
    code: 'MOCK-CONTENT-1',
    source: 'MANUAL',
    status: 'DRAFT',
    demoOnly: true,
    currentVersion: 1,
    currentRubricVersion: 1,
    publishedVersion: null,
          publishedRubricVersion: null,
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
        answerUnit: null,
        inputTemplate: [],
        sceneUri: '',
        staticSceneUri: '',
        achievementStandards: ['4과03-01'],
        achievementLevels: { '4과03-01': 'B' },
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
            standardCode: '4과03-01',
          },
        ],
        exampleAnswer: '한쪽 잎은 더 넓고 다른 쪽 잎은 길쭉합니다.',
        forbiddenTerms: ['예시 답'],
        hints: ['잎의 크기와 모양을 각각 살펴보세요.'],
        keywords: ['잎(잎사귀)', '넓다(넓적하다)'],
        essayType: null,
      },
    ],
    reviews: [],
  },
]
const standard = (code: string, subject: string, gradeBand: AchievementStandard['gradeBand'], area: string, statement: string): AchievementStandard => ({
  code, subject, gradeBand, area, statement, levelScale: gradeBand === '중1~3' ? 5 : 3, levels: null,
  curriculumVersion: '2022 개정', source: '교육부 고시 제2022-33호', note: null,
})
/** 성취기준 표 일부 (learning db/seed/achievement_standards.sql에서 옮김, 실제 표는 765개) */
export const achievementStandards: AchievementStandard[] = [
  standard('4과01-01', '과학', '초3~4', '힘과 우리 생활', '일상생활에서 힘과 관련된 현상에 흥미를 갖고, 물체를 밀거나 당길 때 나타나는 현상을 관찰할 수 있다.'),
  standard('4과01-02', '과학', '초3~4', '힘과 우리 생활', '수평잡기 활동을 통해 물체의 무게를 비교할 수 있다.'),
  standard('4과03-01', '과학', '초3~4', '식물의 생활', '여러 가지 식물을 관찰하여 특징에 따라 식물을 분류할 수 있다.'),
  standard('4과03-02', '과학', '초3~4', '식물의 생활', '다양한 환경에 서식하는 식물을 조사하여 식물의 생김새와 생활 방식이 환경과 관련되어 있음을 설명할 수 있다.'),
  standard('4국01-01', '국어', '초3~4', '듣기⋅말하기', '중요한 내용과 주제를 파악하며 듣고 그 내용을 요약한다.'),
  standard('4국01-02', '국어', '초3~4', '듣기⋅말하기', '원인과 결과의 관계를 고려하여 내용을 예측하며 듣고 말한다.'),
  standard('4수01-02', '수학', '초3~4', '수와 연산', '다섯 자리 이상의 수의 범위에서 수의 계열을 이해하고, 수의 크기를 비교하며 그 방법을 설명할 수 있다.'),
  standard('6과01-02', '과학', '초5~6', '지층과 화석', '지층이 퇴적암으로 이루어짐을 알고, 퇴적암을 알갱이의 크기에 따라 분류할 수 있다.'),
  standard('6국01-02', '국어', '초5~6', '듣기⋅말하기', '주장을 파악하고 이유나 근거가 타당한지 평가하며 듣는다.'),
  standard('6국02-01', '국어', '초5~6', '읽기', '글의 구조를 고려하며 주제나 주장을 파악하고 글 내용을 요약한다.'),
  standard('6수01-01', '수학', '초5~6', '수와 연산', '덧셈, 뺄셈, 곱셈, 나눗셈의 혼합 계산에서 계산하는 순서를 알고, 혼합 계산을 할 수 있다.'),
  standard('9국01-01', '국어', '중1~3', '듣기⋅말하기', '화자의 의도와 관점을 추론하며 듣는다.'),
]
const draftBase = (draftId: string, input: MissionDraft['input']): MissionDraft => ({
  draftId, status: 'GENERATING', attempts: 0, maxAttempts: 3, input, checkResults: [], draft: null, failureCode: null,
  versions: { prompt: null, model: null }, missionId: null, requestedBy: 'mock-admin', createdAt: '2026-11-08T10:00:00+09:00',
  updatedAt: '2026-11-08T10:01:00+09:00',
})
/** 미션 초안 (state-diagram 3.4). 생성 중 초안은 목업 핸들러가 조회 때 진행시킴 */
export const missionDrafts: MissionDraft[] = [
  {
    ...draftBase('draft-ready', { standardCodes: ['6국01-02'], achievementLevels: { '6국01-02': 'B' }, thinkingType: 'EVALUATE', gradeMin: 5, gradeMax: 6, inputType: 'NARRATIVE' }),
    status: 'READY', attempts: 2,
    checkResults: [{ attempt: 1, failures: [{ check: 'LEAK', reason: 'EXAMPLE_ANSWER' }] }],
    versions: { prompt: 'mission-draft-mock-1', model: 'mock-model' },
    draft: {
      title: '급식 메뉴 투표, 어떻게 정할까?', question: '친구의 주장과 근거를 듣고, 근거가 타당한지 평가해 보세요.',
      guide: '주장과 근거를 나누어 생각해 보세요.', sceneNote: '교실 칠판에 메뉴 투표판', choices: null, categories: null, answerKey: null,
      exampleAnswer: '친구는 인기 메뉴를 골라야 한다고 주장했지만, 영양을 따지지 않아 근거가 부족합니다.',
      forbiddenTerms: ['정답'], hints: ['친구가 말한 까닭은 무엇인가요?'],
      elements: [
        { code: 'EVALUATE_CLAIM', label: '주장', description: '친구 주장을 밝힘', goodThought: true, standardCode: '6국01-02' },
        { code: 'EVALUATE_EVIDENCE', label: '근거', description: '근거의 타당성을 평가함', goodThought: true, standardCode: '6국01-02' },
      ],
    },
  },
  {
    ...draftBase('draft-check-failed', { standardCodes: ['4과03-01'], achievementLevels: null, thinkingType: 'ANALYZE', gradeMin: 3, gradeMax: 4, inputType: 'CHOICE' }),
    status: 'CHECK_FAILED', attempts: 3, versions: { prompt: 'mission-draft-mock-1', model: 'mock-model' },
    checkResults: [
      { attempt: 1, failures: [{ check: 'REQUIRED', reason: 'CHOICES' }] },
      { attempt: 2, failures: [{ check: 'ELEMENT_CODE', reason: 'rubric.elements.code' }] },
      { attempt: 3, failures: [{ check: 'QUESTION_LENGTH', reason: 'TOO_LONG' }] },
    ],
    draft: {
      title: '잎 모양 고르기', question: '아주 긴 질문'.repeat(30), guide: null, sceneNote: null,
      choices: [{ id: 'c1', label: '넓은 잎' }, { id: 'c2', label: '바늘잎' }], categories: null, answerKey: { choiceIds: ['c1'] },
      exampleAnswer: null, forbiddenTerms: [], hints: ['잎의 넓이를 보세요.'],
      elements: [{ code: 'ANSWER_KEY', label: '정답', description: '고른 답이 정답과 같음', goodThought: true, standardCode: null }],
    },
  },
  {
    ...draftBase('draft-failed', { standardCodes: ['4수01-02'], achievementLevels: { '4수01-02': 'A' }, thinkingType: 'SOLVE', gradeMin: 3, gradeMax: 4, inputType: 'SOLUTION_STEPS' }),
    status: 'FAILED', attempts: 3, failureCode: 'AI_TIMEOUT',
    checkResults: [1, 2, 3].map((attempt) => ({ attempt, failures: [{ check: 'AI_CALL', reason: 'AI_TIMEOUT' }] })),
  },
]
export const audits: Audit[] = []
export function audit(
  action: string,
  targetType: string,
  targetId: string,
  result: 'SUCCESS' | 'FAILURE',
  detail: string | Record<string, unknown>,
) {
  audits.unshift({
    id: crypto.randomUUID(),
    actorUserId: 'mock-admin',
    action,
    targetType,
    targetId,
    result,
    createdAt: stamp(),
      ...(targetType === 'MODEL_VERSION' && typeof detail === 'object' ? { detail } : {}),
  })
}
// active: 지금 쓰는 버전만 현재 범위를 가짐, revision: 같은 종류·이름 안의 변경 순번 (core 규칙)
const demoEvaluation = (approved: boolean, active = false, revision = approved ? 1 : 0) => ({
  evidence: { datasetId:'demo-only',datasetVersion:'v1',baselineVersion:'baseline-v1',comparisonReport:'개발용 예시 · 실제 성능 승인 아님',trainingEvaluationSeparation:'가상 평가 자료',quoteAccuracy:'시연 기록',calculationAccuracy:'시연 기록',humanReview:'시연 검토',evaluatedScopes:['judgment/grade-3/narrative'] },
  approval: approved ? { scopes:['judgment/grade-3/narrative'],reason:'개발용 예시',approvedBy:'mock-reviewer',approvedAt:stamp() } : null,
  activeScopes: active ? ['judgment/grade-3/narrative'] : [],revision,
})
export const modelVersions: ModelVersion[] = [
  {
    id: 'prompt-1',
    kind: 'PROMPT',
    name: 'judge',
    version: 'mock-1',
    status: 'ACTIVE',
    evalResult: demoEvaluation(true, true, 2),
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
    evalResult: demoEvaluation(true, false, 1),
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
