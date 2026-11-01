import type { Mission, Reflection } from './classroom.ts'

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
