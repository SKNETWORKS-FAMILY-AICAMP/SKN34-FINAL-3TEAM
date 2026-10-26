import { QueryClient } from '@tanstack/react-query'

// 서버 상태는 TanStack Query로만 관리 (아키텍처 3장)
export const queryClient = new QueryClient()
