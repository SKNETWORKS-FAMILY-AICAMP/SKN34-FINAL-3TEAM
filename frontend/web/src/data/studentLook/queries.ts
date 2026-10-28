import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { studentLookApi } from './api.ts'
import type { StudentLook } from '../../domain/studentLook.ts'

const key = (childId: string | undefined) => ['student-look', childId] as const

/** 학생 본인 설정. 받기 전·실패 시 화면은 기본 테마로 그린다(설정은 학습을 막지 않는다). */
export function useStudentLook(childId: string | undefined) {
  return useQuery({
    queryKey: key(childId),
    queryFn: ({ signal }) => studentLookApi.get(signal),
    enabled: !!childId,
    retry: false,
    staleTime: Infinity,
  })
}

/** 고르는 즉시 화면에 반영하고, 저장 실패 시 이전 설정으로 되돌린다. */
export function useSaveLook(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (look: Pick<StudentLook, 'theme' | 'companion'>) => studentLookApi.save(look),
    onMutate: async (look) => {
      await cache.cancelQueries({ queryKey: key(childId) })
      const before = cache.getQueryData<StudentLook>(key(childId))
      cache.setQueryData<StudentLook>(key(childId), {
        updatedAt: before?.updatedAt ?? null,
        ...look,
      })
      return { before }
    },
    onError: (_e, _look, context) => {
      if (context?.before) cache.setQueryData(key(childId), context.before)
      else cache.removeQueries({ queryKey: key(childId) })
    },
    onSuccess: (saved) => cache.setQueryData(key(childId), saved),
  })
}
