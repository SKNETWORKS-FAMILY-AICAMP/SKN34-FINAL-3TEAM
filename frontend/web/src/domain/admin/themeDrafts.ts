import { inputLabels } from '../classroom.ts'
import type { InputType, ThinkingType } from '../classroom.ts'
import { THINKING_ORDER } from '../studentLook.ts'
import type { GradeBand } from './retention.ts'
import { draftStatusLabels } from './missionStandards.ts'
import type { MissionDraftStatus } from './missionStandards.ts'

/** core #439와 api-spec 2.8에 확정된 값만 사용한다. #438 상세 DTO는 여기서 정하지 않는다. */
export type ThemeDraftStatus = MissionDraftStatus
export const themeDraftLabels = draftStatusLabels
export const themeDraftSourceLabels = { AUTO: '주간 자동', ADMIN: '관리자 요청' } as const
export interface ThemeDraftRequest {
  gradeBand: GradeBand
  weekStart: string
  topic?: string
  missions?: { thinkingType: ThinkingType; standardCodes: string[]; inputType: InputType }[]
}
export interface ThemeDraft { draftId: string; status: ThemeDraftStatus }
export function themeDraftOf(raw: unknown): ThemeDraft {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('테마 초안 응답을 확인하지 못했습니다.')
  const value = raw as Record<string, unknown>
  if (typeof value.draftId !== 'string' || !value.draftId || typeof value.status !== 'string' || !Object.hasOwn(themeDraftLabels, value.status))
    throw new Error('테마 초안 응답을 확인하지 못했습니다.')
  return { draftId: value.draftId, status: value.status as ThemeDraftStatus }
}
export function themeDraftRequestErrors(req: ThemeDraftRequest): string[] {
  const errors: string[] = []
  if (!['G3_4', 'G5_6'].includes(req.gradeBand)) errors.push('학년군을 선택해 주세요.')
  const date = new Date(req.weekStart + 'T00:00:00Z')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(req.weekStart) || !Number.isFinite(date.valueOf()) || date.toISOString().slice(0, 10) !== req.weekStart || date.getUTCDay() !== 1)
    errors.push('적용 주의 월요일을 선택해 주세요.')
  if (new Set(req.missions?.map(m => m.thinkingType)).size !== (req.missions?.length ?? 0)) errors.push('같은 생각 유형은 한 번만 지정해 주세요.')
  for (const m of req.missions ?? []) {
    if (!THINKING_ORDER.includes(m.thinkingType)) errors.push('생각 유형을 확인해 주세요.')
    if (!Object.hasOwn(inputLabels, m.inputType)) errors.push('입력 방식을 확인해 주세요.')
    if (!m.standardCodes.length || m.standardCodes.some(code => !code.trim() || code.includes('[') || code.includes(']') || /\s/.test(code))) errors.push('직접 지정한 유형은 성취기준 표에서 코드를 골라 주세요.')
    if (req.gradeBand === 'G3_4' && m.inputType === 'ESSAY') errors.push('초3~4에는 논술을 지정할 수 없습니다.')
  }
  return [...new Set(errors)]
}
