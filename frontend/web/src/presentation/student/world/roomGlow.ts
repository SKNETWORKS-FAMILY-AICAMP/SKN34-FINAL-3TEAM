import { useEffect, useState } from 'react'
import type { RoomSlot } from './roomAssets.ts'

/** 고른 칸의 가구가 반짝이는 시간(ms). room.css st-room-glow와 같게 */
export const GLOW_MS = 1600

/**
 * 고른 칸이 바뀔 때마다 그 칸 이름을 잠깐 돌려준다(가구 반짝임용). 같은 칸을 다시 골라도 n이 바뀌어 다시 반짝인다.
 */
export function useGlow() {
  const [glow, setGlow] = useState<{ slot: RoomSlot; n: number } | null>(null)
  useEffect(() => {
    if (!glow) return
    const id = window.setTimeout(() => setGlow(null), GLOW_MS)
    return () => window.clearTimeout(id)
  }, [glow])
  return { glow, flash: (slot: RoomSlot) => setGlow((g) => ({ slot, n: (g?.n ?? 0) + 1 })) }
}

/**
 * 방 그림의 면 목록. 반짝이는 칸의 면은 key에 n을 붙여 다시 그려 애니메이션이 처음부터 돈다.
 * 내 방(StudentRoom) 방 꾸미기 서랍에서 쓴다.
 */
export function glowClass(part: RoomSlot | undefined, glow: { slot: RoomSlot; n: number } | null) {
  return part && glow?.slot === part ? { cls: ' is-glow', suffix: `-g${glow.n}` } : { cls: '', suffix: '' }
}

