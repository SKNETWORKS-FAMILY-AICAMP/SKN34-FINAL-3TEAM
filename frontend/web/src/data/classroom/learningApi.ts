import { apiFetch, ApiError } from '../apiClient.ts'
import type { Reflection } from '../../domain/classroom.ts'
import { difficultyCodes } from '../../domain/learning.ts'
import type { SelfAssessment } from '../../domain/learning.ts'
import type { AttemptComparison, ComparisonSnapshot } from '../../domain/learning.ts'

export async function getAttemptComparison(id: string, signal?: AbortSignal): Promise<AttemptComparison> {
  const value = await apiFetch<AttemptComparison>(`/attempts/${encodeURIComponent(id)}/comparison`, { signal, cache: 'no-store' })
  const snapshot = (s: ComparisonSnapshot | null) => !!s && typeof s.attemptId === 'string' &&
    typeof s.finishedAt === 'string' && Number.isFinite(Date.parse(s.finishedAt)) &&
    !!s.mission && typeof s.mission.title === 'string' && typeof s.mission.question === 'string' &&
    ['CHOICE', 'ORDERING', 'CLASSIFICATION', 'NARRATIVE', 'SOLUTION_STEPS', 'ESSAY'].includes(s.mission.inputType) &&
    Array.isArray(s.mission.choices) && s.mission.choices.every(c => !!c && typeof c.id === 'string' && typeof c.label === 'string') &&
    [null, 'CORRECT', 'PARTIAL', 'RETHINK', 'HELD'].includes(s.judgment) && Array.isArray(s.elements) &&
    Array.isArray(s.answers) && s.answers.every(a => typeof a.answerId === 'string' && Number.isInteger(a.version) && a.version > 0 &&
      (a.text === null || typeof a.text === 'string') && !!a.content && typeof a.content === 'object' && !Array.isArray(a.content))
  const valid = value?.attemptId === id && snapshot(value.current) && value.current.attemptId === id &&
    ['NO_PREVIOUS', 'COMPARABLE', 'CRITERIA_CHANGED'].includes(value.state) && Array.isArray(value.elements) &&
    (value.state === 'NO_PREVIOUS' ? value.previous === null && value.elements.length === 0 : snapshot(value.previous) && value.previous!.attemptId !== id) &&
    (value.state !== 'CRITERIA_CHANGED' || value.elements.length === 0) && value.elements.every(e =>
      typeof e.elementId === 'string' && typeof e.label === 'string' && typeof e.previousSatisfied === 'boolean' &&
      typeof e.currentSatisfied === 'boolean' && ['ADDED', 'RETAINED', 'NOT_CONFIRMED', 'NOT_CONFIRMED_NOW'].includes(e.change) && e.change ===
        (e.currentSatisfied ? e.previousSatisfied ? 'RETAINED' : 'ADDED' : e.previousSatisfied ? 'NOT_CONFIRMED_NOW' : 'NOT_CONFIRMED'))
  if (!valid) throw new ApiError({ status: 502, code: 'CONTRACT_NOT_READY', title: '이전 결과 비교 응답을 확인하지 못했습니다.' })
  return value
}

export async function saveReflection(id: string, reflection: Reflection) {
  const difficulty = difficultyCodes[reflection.difficulty]
  if (!difficulty) throw new Error('돌아보기 난이도를 선택해 주세요.')
  await apiFetch(`/attempts/${encodeURIComponent(id)}/reflection`, {
    method: 'POST', body: JSON.stringify({ difficulty, text: reflection.text }),
  })
}
export async function saveSelfAssessment(id: string, checks: { elementId: string; checked: boolean }[]) {
  const raw = await apiFetch<unknown>(`/attempts/${encodeURIComponent(id)}/self-assessment`, {
    method: 'POST', body: JSON.stringify({ checks }),
  })
  if (!Array.isArray(raw) || raw.some((e) => !e || typeof e.elementId !== 'string' ||
      typeof e.label !== 'string' || (e.selfChecked !== null && typeof e.selfChecked !== 'boolean') ||
      typeof e.aiChecked !== 'boolean' || (e.quote !== null && typeof e.quote !== 'string')) ||
      new Set(raw.map((e) => e.elementId)).size !== raw.length)
    throw new ApiError({ status: 502, code: 'CONTRACT_NOT_READY', title: '자기 평가 응답을 확인하지 못했습니다.' })
  return raw as SelfAssessment[]
}
