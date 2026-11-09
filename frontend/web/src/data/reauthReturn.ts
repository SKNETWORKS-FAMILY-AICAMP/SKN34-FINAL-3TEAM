import { useEffect, useRef } from 'react'

/**
 * Google 재인증 새 탭 → 원래 탭 복귀 (#425).
 * 콜백 페이지(core `/api/v1/auth/google/reauth/callback`)가 같은 출처 BroadcastChannel로 challengeId를 알린다.
 * 팝업은 opener=null이라 postMessage를 쓸 수 없다. 채널에는 challengeId만 오고 토큰은 오지 않는다.
 */
export const REAUTH_CHANNEL = 'sagomungchi-reauth'

type ChannelLike = { onmessage: ((event: MessageEvent) => void) | null; close: () => void }

/** 자기 challengeId 알림을 한 번만 받아 onReturn을 부른다. BroadcastChannel이 없으면 아무것도 하지 않는다. */
export function subscribeReauthReturn(
  challengeId: string,
  onReturn: () => void,
  open: (name: string) => ChannelLike | null = (name) => (typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(name)),
): () => void {
  if (!challengeId) return () => {}
  const channel = open(REAUTH_CHANNEL)
  if (!channel) return () => {}
  let closed = false
  const close = () => { if (!closed) { closed = true; channel.onmessage = null; channel.close() } }
  channel.onmessage = (event) => {
    const data = event.data as { type?: unknown; challengeId?: unknown } | null
    if (data?.type !== 'REAUTH_VERIFIED' || data.challengeId !== challengeId) return
    close()
    onReturn()
  }
  return close
}

/** active인 동안 challengeId 알림이 오면 onReturn(보통 finishReauth)을 자동 호출한다. 수동 "완료 확인"은 그대로 둔다. */
export function useReauthReturn(challengeId: string, active: boolean, onReturn: () => void) {
  const latest = useRef(onReturn)
  useEffect(() => { latest.current = onReturn })
  useEffect(() => {
    if (!active) return
    return subscribeReauthReturn(challengeId, () => latest.current())
  }, [challengeId, active])
}
