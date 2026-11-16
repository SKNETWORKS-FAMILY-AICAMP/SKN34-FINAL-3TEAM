import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
export function useAdminMutation<T, V>(fn: (v: V) => Promise<T>) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ['admin'] })
    },
  })
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
