import { useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { MutateOptions } from '@tanstack/react-query'
import { adminApi } from './api.ts'
export function useAdminQuery<T>(
  key: unknown[],
  fn: (signal: AbortSignal) => Promise<T>,
  enabled = true,
  /** 데이터에 따라 다시 조회할 간격(ms). false면 멈춤 (미션 초안 생성 중 확인) */
  poll?: (data: T | undefined) => number | false,
) {
  return useQuery({
    queryKey: ['admin', ...key],
    queryFn: ({ signal }) => fn(signal),
    enabled,
    retry: false,
    ...(poll ? { refetchInterval: (q: { state: { data: T | undefined } }) => poll(q.state.data) } : {}),
  })
}
/**
 * 관리자 변경 요청. 처리 중 단추는 초점을 지키려고 끄지 않으므로(#917) 처리 중에 다시 부르면
 * 두 번째 요청을 보내지 않는다. 무시된 `mutateAsync`는 끝나지 않는 Promise라 성공·실패 처리가 두 번 돌지 않는다.
 */
export function useAdminMutation<T, V>(fn: (v: V) => Promise<T>) {
  const cache = useQueryClient()
  const running = useRef(false)
  const mutation = useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ['admin'] })
    },
  })
  const { mutateAsync: send } = mutation
  const mutateAsync = useCallback((v: V, options?: MutateOptions<T, Error, V>) => {
    if (running.current) return new Promise<T>(() => {})
    running.current = true
    return send(v, options).finally(() => { running.current = false })
  }, [send])
  const mutate = useCallback((v: V, options?: MutateOptions<T, Error, V>) => {
    mutateAsync(v, options).catch(() => {})
  }, [mutateAsync])
  return { ...mutation, mutate, mutateAsync }
}

/** 미션에 저장된 성취기준 코드의 표 행 (표에 없는 코드는 빠짐). 미션 편집·검토·초안 요청이 같은 키로 공유 */
export function useStandardsByCodes(codes: string[]) {
  const key = [...new Set(codes.filter((c) => c.trim()))].sort()
  return useAdminQuery(['standards-by-code', key], (signal) => adminApi.standardsByCodes(key, signal), key.length > 0)
}

/** scoring Pod 모델 로딩 보고 (#370). 15초마다 다시 조회 */
export function useModelLoading() {
  return useAdminQuery(['model-loading'], (signal) => adminApi.modelLoading(signal), true, () => 15000)
}
