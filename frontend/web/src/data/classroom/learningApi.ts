import { apiFetch, ApiError } from '../apiClient.ts'
import type { Reflection } from '../../domain/classroom.ts'
import { difficultyCodes } from '../../domain/learning.ts'
import type { SelfAssessment } from '../../domain/learning.ts'

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
