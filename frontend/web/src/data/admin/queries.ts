import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
export function useAdminQuery<T>(
  key: unknown[],
  fn: (signal: AbortSignal) => Promise<T>,
  enabled = true,
) {
  return useQuery({
    queryKey: ['admin', ...key],
    queryFn: ({ signal }) => fn(signal),
    enabled,
    retry: false,
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
