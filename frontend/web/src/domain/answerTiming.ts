import type { AnswerContent, InputType } from './classroom.ts'

/**
 * 답변 생각·작성 시간(P28, api-spec 3.1, 에픽 #799).
 * 생각 = 문제 화면(보완 답변은 되묻기 질문) 표시 → 답변 칸 첫 입력, 작성 = 첫 입력 → 제출.
 * 시각은 기기 시계가 아니라 performance.now() 경과 시간(밀리초)으로 받는다. 학생 화면에는 보여 주지 않는다.
 */
export interface AnswerTiming {
  thinkingSeconds: number | null
  writingSeconds: number | null
}
export const noTiming: AnswerTiming = { thinkingSeconds: null, writingSeconds: null }
/** 0 미만·24시간 초과는 서버가 둘 다 null로 저장하므로(3.1) 웹도 같은 범위 밖 값은 보내지 않는다 */
export const MAX_TIMING_SECONDS = 86400
const TEXT_TYPES: InputType[] = ['NARRATIVE', 'SOLUTION_STEPS', 'ESSAY']
export const isTimedInput = (type: InputType) => TEXT_TYPES.includes(type)

/** 답변 칸 글(보호자 받아쓰기 표시·고르기 값 제외). 이 값이 바뀌면 첫 입력으로 본다(시작 문장·메모 넣기 버튼 포함) */
export const typedText = (a: AnswerContent) =>
  JSON.stringify([a.text, a.finalAnswer, a.steps, a.essay])
export const hasTypedText = (a: AnswerContent) =>
  !!(a.text.trim() || a.finalAnswer.trim() || a.steps.some((s) => s.trim()) ||
    a.essay.claim.trim() || a.essay.reasons.some((r) => r.trim()) || a.essay.rebuttal.trim())

/** 한 답변(최초 또는 되묻기 한 번)을 쓰는 동안의 측정 상태 */
export interface TimingRound {
  /** 'first' 또는 되묻기 followupId 등 이 답변 차례를 구분하는 값 */
  round: string
  shownAt: number
  firstInputAt: number | null
  /** 새로고침 뒤 이어하기처럼 첫 입력 시각을 모르는 차례 */
  resumed: boolean
}
export function startRound(round: string, now: number, resumed: boolean): TimingRound {
  return { round, shownAt: now, firstInputAt: null, resumed }
}
export function markInput(r: TimingRound, before: AnswerContent, after: AnswerContent, now: number): TimingRound {
  if (r.firstInputAt != null || typedText(before) === typedText(after)) return r
  return { ...r, firstInputAt: now }
}
export function measureTiming(r: TimingRound | null, answer: AnswerContent, submitAt: number): AnswerTiming {
  if (!r || r.resumed || r.firstInputAt == null || answer.dictatedByGuardian || !isTimedInput(answer.inputType))
    return noTiming
  const thinking = Math.round((r.firstInputAt - r.shownAt) / 1000)
  const writing = Math.round((submitAt - r.firstInputAt) / 1000)
  const ok = (s: number) => Number.isInteger(s) && s >= 0 && s <= MAX_TIMING_SECONDS
  // 두 값은 함께 있거나 함께 없다(ERD 쌍 CHECK)
  return ok(thinking) && ok(writing) ? { thinkingSeconds: thinking, writingSeconds: writing } : noTiming
}
