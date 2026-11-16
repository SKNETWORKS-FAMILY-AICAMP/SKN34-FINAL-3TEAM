import { useRef, useState } from 'react'
import { useSaveLook, useStudentLook } from '../../../data/studentLook/queries.ts'
import { useLookItems, useMyPoints, useUnlock } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { FRIENDS } from '../../../domain/studentLook.ts'
import type { CompanionId, ThemeId } from '../../../domain/studentLook.ts'
import { companionKey, isLookUnlocked, NO_EQUIPPED, themeKey, wornAssets } from '../../../domain/retention.ts'
import type { Equipped, LookItem } from '../../../domain/retention.ts'
import { useLook } from './lookContext.ts'

export const unlockMessage = (e: unknown) => {
  const code = e instanceof ApiError ? e.problem.code : ''
  if (code === 'INSUFFICIENT_POINTS') return '포인트가 조금 모자라요. 미션을 끝내면 포인트가 쌓여요.'
  if (code === 'LOOK_ITEM_NOT_ON_SALE') return '지금은 해금할 수 없는 꾸미기예요.'
  if (code === 'LOOK_LOCKED') return '아직 해금하지 않은 꾸미기예요. 목록을 다시 확인해 주세요.'
  if (code === 'LOOK_ITEM_NOT_FOUND') return '이 꾸미기를 찾지 못했어요. 목록을 다시 확인해 주세요.'
  return null
}
/** 서버 아이템 이름 대신 화면 이름을 쓴다: 동행 캐릭터는 뭉치 친구 이름(#648) */
export const itemName = (item: LookItem) => {
  const friend = item.slot === 'COMPANION' && FRIENDS.find((f) => f.companion && companionKey(f.companion) === item.itemKey)
  return friend ? friend.name : item.name
}

/**
 * 꾸미기·뭉치 친구들이 같이 쓰는 고르기·해금 상태 (API 명세 2.10·3.12, P22).
 * 호수·뭉치는 처음부터 열려 있고, 나머지는 포인트로 한 번 해금하면 계속 쓸 수 있다(되돌리기·환급 없음).
 * #389의 해금 확정 응답과 소유 목록을 기준으로 선택·착용한다. 해금은 확인 단계를 거치고, 응답 유실 뒤에도 같은 항목은 같은 멱등 키로 다시 보낸다.
 */
export function useLookShop(child: Child) {
  const { t, companion } = useLook()
  const save = useSaveLook(child.id)
  const settings = useStudentLook(child.id)
  const look = settings.data
  const items = useLookItems(child.id)
  const points = useMyPoints(child.id)
  const unlock = useUnlock(child.id)
  const [confirming, setConfirming] = useState<string | null>(null)
  const unlockKeys = useRef(new Map<string, string>())
  const catalog = items.error ? undefined : items.data
  const equipped: Equipped = look?.equipped ?? NO_EQUIPPED
  // 미리보기는 지금 고른 착용 그대로(#455). 그림 파일이 없으면 기본 모습
  const worn = wornAssets(equipped, catalog)
  const balance = !points.error ? points.data?.balance : undefined
  const busy = save.isPending || unlock.isPending
  const choosingBlocked = busy || settings.isPending || settings.isError || confirming !== null
  const pendingItem = catalog?.find((i) => i.itemKey === confirming)
  const affordable = !!pendingItem && balance !== undefined && balance >= pendingItem.pricePoints
  const choose = (next: { theme?: ThemeId; companion?: CompanionId; equipped?: Equipped }) => {
    if (choosingBlocked) return
    unlock.reset() // 고르는 순간에는 저장 상태만 보이게 한다.
    save.mutate({
      theme: next.theme ?? t.id,
      companion: next.companion ?? companion,
      ...(next.equipped ? { equipped: next.equipped } : {}),
    })
  }
  const locked = (itemKey: string) => !isLookUnlocked(catalog, itemKey) &&
    !(!catalog && look && (itemKey === themeKey(look.theme) || itemKey === companionKey(look.companion)))
  const price = (itemKey: string) => catalog?.find((i) => i.itemKey === itemKey)?.pricePoints ?? 0
  const onSale = (itemKey: string) => !!catalog?.some((i) => i.itemKey === itemKey && i.onSale)
  const startUnlock = (itemKey: string) => { save.reset(); unlock.reset(); setConfirming(itemKey) }
  const cancelUnlock = () => { setConfirming(null); unlock.reset() }
  /** 응답 유실 뒤에도 같은 항목은 같은 키로 재전송한다. */
  function confirmUnlock() {
    if (!pendingItem || !affordable || busy || !pendingItem.onSale || pendingItem.unlocked) return
    const itemKey = pendingItem.itemKey
    let key = unlockKeys.current.get(itemKey)
    if (!key) { key = crypto.randomUUID(); unlockKeys.current.set(itemKey, key) }
    unlock.mutate({ itemKey, key }, { onSuccess: () => {
      unlockKeys.current.delete(itemKey)
      setConfirming(null)
    } })
  }
  return {
    t, companion, look, settings, items, points, save, unlock, catalog, equipped, worn, balance, busy, choosingBlocked,
    confirming, pendingItem, affordable, choose, locked, price, onSale, startUnlock, cancelUnlock, confirmUnlock,
  }
}
export type LookShop = ReturnType<typeof useLookShop>

/** 화면 테마별 바깥 틀 색(student-world.css `[data-theme]`의 --sk-frame과 같은 값). 꾸미기 미리 보기가 고르는 중인 테마 색을 칠한다 */
export const THEME_FRAME: Record<ThemeId, string> = { lake: '#3eafed', forest: '#6dbf5a', factory: '#8fa8cc', space: '#a47bea', sea: '#1bbbd4' }

export type CustomizeTab = 'theme' | 'friend' | 'wear' | 'furniture'
/** 꾸미기 탭 4개(#648 시안 Customize). question은 탭 안 고르기 영역 이름 */
export const CUSTOMIZE_TABS: { id: CustomizeTab; label: string; question: string }[] = [
  { id: 'theme', label: '화면 테마', question: '어떤 색으로 꾸밀까?' },
  { id: 'friend', label: '캐릭터', question: '누구랑 같이 다닐까?' },
  { id: 'wear', label: '옷 입히기', question: '친구에게 입혀 볼까?' },
  { id: 'furniture', label: '내 방 가구', question: '내 방 가구를 바꿔 볼까?' },
]
export const isCustomizeTab = (v: string | null): v is CustomizeTab => CUSTOMIZE_TABS.some((tab) => tab.id === v)

