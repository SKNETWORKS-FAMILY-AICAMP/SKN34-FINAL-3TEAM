import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from './apiClient.ts'
import { useParentQuery } from './parent/queries.ts'
import { serviceApi } from './serviceApi.ts'
import { streamSse } from './sse.ts'

/** 다시 연결하기 전 대기. 정상 종료(서버 최대 5분 연결) 뒤에는 1초, 실패가 이어지면 30초까지 늘린다. */
export const reconnectDelay = (failures: number) => Math.min(30_000, 1000 * 2 ** failures)

const wait = (ms: number, signal: AbortSignal) => new Promise<void>(resolve => {
  const timer = setTimeout(resolve, ms)
  signal.addEventListener('abort', () => { clearTimeout(timer); resolve() }, { once: true })
})

/**
 * 학부모·관리자 로그인 중 알림 스트림 1개 (API 명세 2.7 SUP-08).
 * `ready`(구독 준비)와 `notification`(새 알림)을 받으면 알림 목록·안 읽은 수를 다시 읽는다.
 * 스트림은 전달 보장이 아니므로 끊겨도 목록 조회는 그대로 동작한다. role이 null이면(학생·로그아웃) 연결하지 않는다.
 */
export function useNotificationStream(role: 'PARENT' | 'ADMIN' | null) {
  const cache = useQueryClient()
  useEffect(() => {
    if (!role) return
    const controller = new AbortController(), { signal } = controller
    const refresh = () => void cache.invalidateQueries({ queryKey: ['parent', 'notifications'] })
    void (async () => {
      let failures = 0
      while (!signal.aborted) {
        let opened = false
        try {
          await streamSse('/notifications/stream', {
            method: 'GET', signal,
            onEvent: ({ event }) => {
              if (event === 'ready') { opened = true; failures = 0 }
              if (event === 'ready' || event === 'notification') refresh()
            },
          })
          if (!opened) failures++
        } catch (error) {
          if (signal.aborted) return
          // 권한·세션 오류는 다시 연결해도 같다. 로그인 상태 처리는 apiClient가 맡는다.
          if (error instanceof ApiError && [401, 403].includes(error.problem.status)) return
          failures++
        }
        await wait(reconnectDelay(failures), signal)
      }
    })()
    return () => controller.abort()
  }, [role, cache])
}

/** 메뉴의 안 읽은 알림. 알림 화면의 "읽지 않은 알림만" 첫 쪽과 같은 캐시를 쓴다. */
export function useUnreadNotifications(enabled: boolean) {
  return useParentQuery(['notifications', true, 0], signal => serviceApi.notifications(true, 0, signal), enabled)
}
