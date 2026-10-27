import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { Scope } from '../../domain/parent.ts'
import { parentApi } from './api.ts'
export function useParentQuery<T>(
  key: unknown[],
  fn: (signal: AbortSignal) => Promise<T>,
  enabled = true,
  poll = false,
) {
  return useQuery({
    queryKey: ['parent', ...key],
    queryFn: ({ signal }) => fn(signal),
    enabled,
    retry: false,
    refetchInterval: (query) =>
      poll &&
      ['RUNNING', 'QUEUED'].includes(
        String((query.state.data as { status?: string } | undefined)?.status),
      )
        ? 1200
        : false,
  })
}
export function useParentMutation<T, V>(fn: (v: V) => Promise<T>) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ['parent'] })
      void cache.invalidateQueries({ queryKey: ['children'] })
    },
  })
}
export function useParentDashboard(scope: Scope) {
  return {
    summary: useParentQuery(['summary', scope], (signal) => parentApi.summary(scope, signal)),
    thinking: useParentQuery(['thinking', scope], (signal) => parentApi.thinking(scope, signal)),
    records: useParentQuery(['records', scope], (signal) => parentApi.records(scope, signal)),
  }
}
