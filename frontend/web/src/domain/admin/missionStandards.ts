import type { InputType, ThinkingType } from '../classroom.ts'

/**
 * 성취기준 표·표준 요소 규칙 (FN 1.5, #262·#336·#356). learning `Standards.kt`의 거울.
 * core가 learning 400 detail을 지워 보내므로(AdminLearningService.sanitize) 저장·요청 전 규칙을 web이 먼저 본다.
 */
export type GradeBand = '초1~2' | '초3~4' | '초5~6' | '중1~3'
/** learning-service.yaml `AchievementStandard`. code는 대괄호 없음, levels는 이용 조건 확인 전 null */
export interface AchievementStandard {
  code: string
  subject: string
  gradeBand: GradeBand
  area: string
  statement: string
  levelScale: 3 | 5
  levels: Record<string, string> | null
  curriculumVersion: string
  source: string
  note: string | null
}
/** 학년군의 학년 범위. 중학교는 7~9로 보아 초3~6 미션과 겹치지 않음 */
export const gradeBands: Record<GradeBand, readonly [number, number]> = {
  '초1~2': [1, 2], '초3~4': [3, 4], '초5~6': [5, 6], '중1~3': [7, 9],
}
/** 미션 학년 범위가 성취기준 학년군 안인지 (#353 학년군 검사) */
export function covers(s: Pick<AchievementStandard, 'gradeBand'>, gradeMin: number, gradeMax: number) {
  const band = gradeBands[s.gradeBand]
  return !!band && gradeMin >= band[0] && gradeMax <= band[1] && gradeMin <= gradeMax
}
/** 미션 학년 범위를 모두 담는 학년군 (없으면 빈 값: 초3~6처럼 두 학년군에 걸침) */
export function bandFor(gradeMin: number, gradeMax: number): GradeBand | '' {
  return (Object.keys(gradeBands) as GradeBand[]).find((b) => covers({ gradeBand: b }, gradeMin, gradeMax)) ?? ''
}
/** 성취수준 단계: 초 3단계 A~C, 중 5단계 A~E */
export const levelOptions = (levelScale: number) => 'ABCDE'.slice(0, levelScale).split('')
export const isLevelShape = (level: string) => /^[A-E]$/.test(level)
export const allowsLevel = (s: Pick<AchievementStandard, 'levelScale'>, level: string) =>
  isLevelShape(level) && levelOptions(s.levelScale).includes(level)

export interface StandardElement { code: string; thinkingType: ThinkingType; label: string; description: string }
/** FN 1.5 표준 요소 표 (#262). learning `StandardElements.ALL`과 같은 순서·문구 */
export const standardElements: StandardElement[] = [
  { code: 'ANALYZE_RELATION', thinkingType: 'ANALYZE', label: '원인·특징·관계', description: '원인과 결과, 특징, 부분 사이의 관계를 말함' },
  { code: 'ANALYZE_REASON', thinkingType: 'ANALYZE', label: '까닭 잇기', description: '말한 원인·특징·관계를 까닭으로 이어 설명함' },
  { code: 'EVALUATE_CLAIM', thinkingType: 'EVALUATE', label: '주장', description: '자기 주장(입장)을 밝힘' },
  { code: 'EVALUATE_EVIDENCE', thinkingType: 'EVALUATE', label: '근거', description: '주장을 뒷받침하는 근거를 말함' },
  { code: 'EVALUATE_PERSPECTIVE', thinkingType: 'EVALUATE', label: '다른 관점·반론', description: '다른 관점·반대 의견·예외를 생각하고 답함' },
  { code: 'CREATE_NEW', thinkingType: 'CREATE', label: '새로운 생각', description: '기존과 다른 새로운 생각을 냄' },
  { code: 'CREATE_WHY', thinkingType: 'CREATE', label: '왜 나은지', description: '자기 생각이 왜 더 나은지 설명함' },
  { code: 'CREATE_CONNECT', thinkingType: 'CREATE', label: '연결·변형', description: '다른 것과 연결하거나 바꾸어 생각을 만듦' },
  { code: 'SOLVE_DEFINE', thinkingType: 'SOLVE', label: '문제 정하기', description: '무엇을 구하거나 해결해야 하는지 말함' },
  { code: 'SOLVE_PLAN', thinkingType: 'SOLVE', label: '방법 세우기', description: '해결 방법이나 순서를 세움' },
  { code: 'SOLVE_CHECK', thinkingType: 'SOLVE', label: '결과 확인', description: '결과가 맞는지 확인함' },
  { code: 'REFLECT_CHANGE', thinkingType: 'REFLECT', label: '바뀐 생각', description: '처음 생각(방법)과 바뀐 생각(방법)을 말함' },
  { code: 'REFLECT_REASON', thinkingType: 'REFLECT', label: '바뀐 까닭', description: '생각이나 방법이 바뀐 까닭을 말함' },
  { code: 'REFLECT_CONNECT', thinkingType: 'REFLECT', label: '생각 과정·경험과 연결', description: '자기 생각 과정이나 경험과 연결해 말함' },
]
export const ANSWER_KEY = 'ANSWER_KEY'
export const FINAL_ANSWER = 'FINAL_ANSWER'
/** 따져 보기 논술은 세 논증 요소를 모두 둔다 (기획서 5.3(3)) */
const argumentCodes = ['EVALUATE_CLAIM', 'EVALUATE_EVIDENCE', 'EVALUATE_PERSPECTIVE']
/** 규칙 판정 입력 방식: 생각 요소를 판정하지 않아 ANSWER_KEY 하나만 둠 */
export const answerKeyInputs: InputType[] = ['CHOICE', 'ORDERING', 'CLASSIFICATION']
const uniqueCode = /^e[1-9][0-9]*$/
const byCode = new Map(standardElements.map((e) => [e.code, e]))

export const isAnswerCode = (code: string) => code === ANSWER_KEY || code === FINAL_ANSWER
/** 저장 때 모양 검사: 표준 코드·`e`+숫자·예약 코드 (learning isValidShape) */
export const isValidElementCode = (code: string) => byCode.has(code) || uniqueCode.test(code) || isAnswerCode(code)

export type ElementKind = 'COMMON' | 'UNIQUE' | 'ANSWER'
export const elementKindLabels: Record<ElementKind, string> = {
  COMMON: '유형 공통 요소', UNIQUE: '성취기준 고유 요소', ANSWER: '정답 요소',
}
/** code 모양으로 요소 종류를 알아냄. 모양이 틀린 옛 code는 null(다시 골라야 함) */
export function elementKind(code: string): ElementKind | null {
  if (byCode.has(code)) return 'COMMON'
  if (uniqueCode.test(code)) return 'UNIQUE'
  if (isAnswerCode(code)) return 'ANSWER'
  return null
}
/** 입력 방식에 맞는 정답 요소 code (서술·논술은 없음) */
export function answerCodeFor(inputType: InputType): string | null {
  if (answerKeyInputs.includes(inputType)) return ANSWER_KEY
  return inputType === 'SOLUTION_STEPS' ? FINAL_ANSWER : null
}
/** 미션 입력 방식에서 고를 수 있는 요소 종류 */
export function kindsFor(inputType: InputType): ElementKind[] {
  if (answerKeyInputs.includes(inputType)) return ['ANSWER']
  return inputType === 'SOLUTION_STEPS' ? ['COMMON', 'UNIQUE', 'ANSWER'] : ['COMMON', 'UNIQUE']
}
export const commonElementsOf = (thinkingType: ThinkingType) => standardElements.filter((e) => e.thinkingType === thinkingType)
/** 다음 성취기준 고유 요소 code: 쓰고 있는 `e`+숫자 중 가장 큰 수 + 1 */
export function nextUniqueCode(codes: string[]) {
  const used = codes.filter((c) => uniqueCode.test(c)).map((c) => Number(c.slice(1)))
  return `e${Math.max(0, ...used) + 1}`
}
/** 요소 종류를 바꿀 때 기본 code: 공통은 아직 안 쓴 그 유형 첫 코드, 고유는 다음 번호, 정답은 입력 방식 코드 */
export function defaultCode(kind: ElementKind, thinkingType: ThinkingType, inputType: InputType, codes: string[]) {
  if (kind === 'UNIQUE') return nextUniqueCode(codes)
  if (kind === 'ANSWER') return answerCodeFor(inputType) ?? ''
  const common = commonElementsOf(thinkingType)
  return (common.find((e) => !codes.includes(e.code)) ?? common[0]).code
}
/** 화면 표시용 요소 code 이름 */
export function elementCodeLabel(code: string) {
  if (code === ANSWER_KEY) return '정답'
  if (code === FINAL_ANSWER) return '최종 답'
  return byCode.get(code)?.label ?? code
}
/**
 * 게시 때 미션 유형·입력 방식에 맞는지 (learning StandardElements.fits). FINAL_ANSWER 위치는 `rubric.elements`가 봄
 * - 표준 코드는 미션과 같은 유형만
 * - 고르기·순서·분류는 ANSWER_KEY 하나만, 그 밖의 입력 방식에는 ANSWER_KEY 없음
 * - 따져 보기 논술은 세 논증 요소 모두
 */
export function elementCodesFit(codes: string[], thinkingType: ThinkingType, inputType: InputType) {
  if (codes.some((c) => !isValidElementCode(c))) return false
  if (codes.some((c) => byCode.has(c) && byCode.get(c)!.thinkingType !== thinkingType)) return false
  if (answerKeyInputs.includes(inputType)) return codes.length === 1 && codes[0] === ANSWER_KEY
  if (codes.includes(ANSWER_KEY)) return false
  if (thinkingType === 'EVALUATE' && inputType === 'ESSAY' && !argumentCodes.every((c) => codes.includes(c))) return false
  return true
}

export type MissionDraftStatus = 'GENERATING' | 'READY' | 'CHECK_FAILED' | 'FAILED' | 'ADOPTED' | 'DISCARDED'
export const draftStatusLabels: Record<MissionDraftStatus, string> = {
  GENERATING: '생성 중', READY: '검사 통과', CHECK_FAILED: '검사 실패', FAILED: '생성 실패', ADOPTED: '채택', DISCARDED: '버림',
}
export const discardableDraft = (s: MissionDraftStatus) => s === 'READY' || s === 'CHECK_FAILED' || s === 'FAILED'
export interface MissionDraftRequest {
  standardCodes: string[]
  achievementLevels: Record<string, string> | null
  thinkingType: ThinkingType
  gradeMin: number
  gradeMax: number
  inputType: InputType
}
export interface GeneratedDraft {
  title: string
  question: string
  guide: string | null
  sceneNote: string | null
  choices: { id: string; label: string }[] | null
  categories: { id: string; label: string }[] | null
  answerKey: { choiceIds?: string[] | null; assignments?: { choiceId: string; categoryId: string }[] | null; finalAnswer?: string | null } | null
  exampleAnswer: string | null
  forbiddenTerms: string[]
  hints: string[]
  elements: { code: string; label: string; description: string; goodThought: boolean; standardCode: string | null }[]
}
/** learning-service.yaml `MissionDraft` (api-spec 4.1, state-diagram 3.4) */
export interface MissionDraft {
  draftId: string
  status: MissionDraftStatus
  attempts: number
  maxAttempts: number
  input: MissionDraftRequest
  checkResults: { attempt: number; failures: { check: string; reason: string }[] }[]
  draft: GeneratedDraft | null
  failureCode: string | null
  versions: { prompt: string | null; model: string | null }
  missionId: string | null
  requestedBy: string
  createdAt: string
  updatedAt: string
}
export const draftCheckLabels: Record<string, string> = {
  REQUIRED: '필수 항목', QUESTION_LENGTH: '질문 길이', LEAK: '정답 노출', STANDARD_CODE: '요소 연결 성취기준',
  ELEMENT_CODE: '요소 code', SHAPE: '미션 모양', AI_CALL: 'AI 호출',
}
export const draftReasonLabels: Record<string, string> = {
  TITLE: '제목', QUESTION: '질문', ELEMENTS: '판정 요소', CHOICES: '선택 항목', CATEGORIES: '분류 그룹',
  ANSWER_KEY: '정답', EXAMPLE_ANSWER: '예시 답', HINTS: '생각 열기 질문', TOO_LONG: '질문이 너무 김',
  FORBIDDEN_TERM: '금지어', AI_TIMEOUT: '응답 시간 초과', AI_UNAVAILABLE: 'AI 사용 불가', AI_BAD_RESPONSE: 'AI 응답 형식 오류',
  AI_CIRCUIT_OPEN: 'AI 호출 일시 중단',
}
/**
 * 초안 요청 전 검사 (learning MissionDraftService.request 400 규칙). standards는 고른 코드의 표 행.
 * 빈 배열이면 통과
 */
export function draftRequestErrors(req: MissionDraftRequest, standards: Record<string, AchievementStandard>): string[] {
  const errors: string[] = []
  if (!req.standardCodes.length) errors.push('성취기준을 1개 이상 고르세요.')
  if (!Number.isInteger(req.gradeMin) || !Number.isInteger(req.gradeMax) || req.gradeMin < 3 || req.gradeMax > 6 || req.gradeMin > req.gradeMax)
    errors.push('학년은 3~6학년, 최소 학년 ≤ 최대 학년이어야 합니다.')
  if (req.inputType === 'ESSAY' && req.gradeMin < 5) errors.push('논술은 5~6학년만 가능합니다.')
  const outside = req.standardCodes.filter((c) => standards[c] && !covers(standards[c], req.gradeMin, req.gradeMax))
  if (outside.length) errors.push(`미션 학년이 성취기준 학년군 밖입니다: ${outside.join(', ')}`)
  const unknown = req.standardCodes.filter((c) => !standards[c])
  if (unknown.length) errors.push(`성취기준 표에 없는 코드입니다: ${unknown.join(', ')}`)
  for (const [code, level] of Object.entries(req.achievementLevels ?? {}))
    if (!standards[code] || !allowsLevel(standards[code], level)) errors.push(`성취수준 단계를 확인하세요: ${code} ${level}`)
  return errors
}
