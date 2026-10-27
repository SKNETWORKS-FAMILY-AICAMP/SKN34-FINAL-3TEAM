import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { queryClient } from './data/queryClient.ts'
import './index.css'
import { router } from './presentation/router.tsx'

async function start() {
  if (import.meta.env.DEV && import.meta.env.VITE_API_MOCK === 'true') {
    const { startMockWorker } = await import('./mocks/browser.ts')
    await startMockWorker()
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  )
}
void start().catch(() => {
  // 목 기동 실패를 실제 서버 호출로 조용히 전환하지 않는다.
  document.getElementById('root')!.textContent =
    '화면을 시작하지 못했습니다. MSW worker 설정을 확인한 뒤 다시 실행해 주세요.'
})
