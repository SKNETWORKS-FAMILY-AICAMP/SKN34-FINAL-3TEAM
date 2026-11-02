import { ApiError } from './apiClient.ts'
import type { PublicAttempt, Reflection } from '../domain/classroom.ts'

export function recordContractError(): never {
  throw new ApiError({ status: 502, code: 'CONTRACT_NOT_READY', title: '학습 기록 응답 계약을 확인해 주세요.' })
}

/** Wire enum/nulls become display values only; submitted answer text is unchanged. */
export function recordReflection(raw: unknown): Reflection | undefined {
  if (raw == null) return undefined
  if (typeof raw !== 'object') return recordContractError()
  const value = raw as Record<string, unknown>
  const labels: Record<string, Reflection['difficulty']> = {
    EASY: '쉬웠어', NORMAL: '보통', HARD: '어려웠어',
    쉬웠어: '쉬웠어', 보통: '보통', 어려웠어: '어려웠어',
  }
  if (typeof value.difficulty !== 'string' || !Object.hasOwn(labels, value.difficulty) ||
      (value.text !== null && typeof value.text !== 'string')) return recordContractError()
  if (value.createdAt !== undefined && (typeof value.createdAt !== 'string' || !Number.isFinite(Date.parse(value.createdAt))))
    return recordContractError()
  return { difficulty: labels[value.difficulty], text: value.text ?? '',
    ...(typeof value.createdAt === 'string' ? { createdAt: value.createdAt } : {}) }
}

export function recordDto(raw: PublicAttempt, studentId: string): PublicAttempt {
  if (raw.studentId !== studentId || !raw.mission || !Array.isArray(raw.answers)) return recordContractError()
  return { ...raw, reflection: recordReflection(raw.reflection) }
}
