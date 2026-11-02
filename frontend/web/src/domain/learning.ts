import type { Mission, Period, Reflection, ThinkingType } from './classroom.ts'
import type { QueryState } from './queryState.ts'

/** FN-DSH-04 학생 생각 활동·돌아보기. 수행한 미션과 본인 돌아보기만 담고 레벨·등급·순위는 없다. */
export interface ThinkingActivity { attemptId: string; thinkingType: ThinkingType; missionTitle: string; reflection: Reflection | null }
export interface ThinkingActivities { state: QueryState; period: Period; items: ThinkingActivity[] }

/** #82 소유 파일을 수정하지 않는 확장 계약. 공통 타입 통합 시 이 확장만 제거합니다. */
export type LearningMission = Mission & { answerUnit?: string | null; inputTemplate?: string[] }
export type DifficultyCode = 'EASY' | 'NORMAL' | 'HARD'
export const difficultyCodes: Record<Reflection['difficulty'], DifficultyCode> = {
  쉬웠어: 'EASY', 보통: 'NORMAL', 어려웠어: 'HARD',
}
export interface SelfAssessment {
  elementId: string
  label: string
  selfChecked: boolean | null
  aiChecked: boolean
  quote: string | null
}

export interface ComparisonSnapshot {
  attemptId: string
  finishedAt: string
  mission: Pick<LearningMission, 'title' | 'question' | 'inputType' | 'choices' | 'categories' | 'answerUnit'>
  judgment: 'CORRECT' | 'PARTIAL' | 'RETHINK' | 'HELD' | null
  answers: { answerId: string; version: number; text: string | null; content: Record<string, unknown> }[]
  elements: import('./classroom.ts').FeedbackElement[]
}
export interface AttemptComparison {
  attemptId: string
  state: 'NO_PREVIOUS' | 'COMPARABLE' | 'CRITERIA_CHANGED'
  previous: ComparisonSnapshot | null
  current: ComparisonSnapshot
  elements: { elementId: string; label: string; previousSatisfied: boolean; currentSatisfied: boolean;
    change: 'ADDED' | 'RETAINED' | 'NOT_CONFIRMED' | 'NOT_CONFIRMED_NOW' }[]
}
export const comparisonLabels = {
  ADDED: '이번에 새로 확인했어요', RETAINED: '이번에도 확인했어요',
  NOT_CONFIRMED: '아직 확인하지 못했어요', NOT_CONFIRMED_NOW: '이번 답에서는 확인하지 못했어요',
} as const

/** 원문이 없는 고르기·분류·풀이·논술도 API의 원본 content로 표시한다. */
export function comparisonAnswerText(answer: ComparisonSnapshot['answers'][number], mission: ComparisonSnapshot['mission']) {
  if (answer.text?.trim()) return answer.text
  const content = answer.content
  const text = (value: unknown) => typeof value === 'string' ? value : ''
  const choice = (id: unknown) => mission.choices?.find(c => c.id === id)?.label ?? text(id)
  if (Array.isArray(content.choiceIds)) return content.choiceIds.map(choice).join(' → ')
  if (Array.isArray(content.assignments)) return content.assignments.map(a => {
    if (!a || typeof a !== 'object') return ''
    return `${choice(a.choiceId)}: ${mission.categories?.find(c => c.id === a.categoryId)?.label ?? text(a.categoryId)}`
  }).filter(Boolean).join('\n')
  if (typeof content.finalAnswer === 'string') return [content.finalAnswer + (mission.answerUnit ?? ''),
    ...(Array.isArray(content.steps) ? content.steps.map(text) : [])].filter(Boolean).join('\n')
  const essay = content.essay as { claim?: unknown; reasons?: unknown; rebuttal?: unknown } | undefined
  if (essay && typeof essay === 'object') return [text(essay.claim), ...(Array.isArray(essay.reasons) ? essay.reasons.map(text) : []), text(essay.rebuttal)].filter(Boolean).join('\n')
  return text(content.text) || '작성한 내용이 없습니다.'
}
