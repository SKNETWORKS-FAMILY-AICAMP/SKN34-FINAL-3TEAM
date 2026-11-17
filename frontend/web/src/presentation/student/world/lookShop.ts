import { useRef, useState } from 'react'
import { useSaveLook, useStudentLook } from '../../../data/studentLook/queries.ts'
import { useLookItems, useMyPoints, usePurchaseDecor, useUnlock } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { FRIENDS } from '../../../domain/studentLook.ts'
import type { CompanionId, ThemeId } from '../../../domain/studentLook.ts'
import { companionKey, DECOR_MAX_OWNED, isLookUnlocked, NO_EQUIPPED, themeKey, wornAssets } from '../../../domain/retention.ts'
import type { Equipped, LookItem } from '../../../domain/retention.ts'
import { useLook } from './lookContext.ts'

export const unlockMessage = (e: unknown) => {
  const code = e instanceof ApiError ? e.problem.code : ''
  if (code === 'INSUFFICIENT_POINTS') return '포인트가 조금 모자라요. 미션을 끝내면 포인트가 쌓여요.'
  if (code === 'LOOK_ITEM_NOT_ON_SALE') return '지금은 해금할 수 없는 꾸미기예요.'
  if (code === 'LOOK_LOCKED') return '아직 해금하지 않은 꾸미기예요. 목록을 다시 확인해 주세요.'
  if (code === 'LOOK_ITEM_NOT_FOUND') return '이 꾸미기를 찾지 못했어요. 목록을 다시 확인해 주세요.'
  // 방 소품 보유 상한(#704, 아이템당 8개)
  if (code === 'LOOK_DECOR_LIMIT') return `이 방 소품은 더 살 수 없어요. ${DECOR_MAX_OWNED}개까지 가질 수 있어요.`
  return null
}

/**
 * 같은 키로 다시 보내야 하는 실패인지. 서버가 요청을 처리했는지 모르는 경우(응답을 못 받음·응답을 읽지 못함·5xx·
 * 로그인 상태가 바뀌어 응답을 버림 401)와 같은 키를 처리 중(409 `IDEMPOTENCY_IN_PROGRESS`)이면 키를 남긴다.
 * 그 밖의 4xx(잔액 부족·판매 중단·보유 상한·없는 항목·키 재사용 등)는 서버가 확정해 거절한 것이라 키를 버린다:
 * 남기면 다음 해금·사기가 같은 키로 나가 같은 거절이나 `IDEMPOTENCY_KEY_REUSED`로 돌아온다.
 */
export const keepIdempotencyKey = (e: unknown) => {
  if (!(e instanceof ApiError)) return true
  const { status, code } = e.problem
  return status >= 500 || status === 401 || code === 'IDEMPOTENCY_IN_PROGRESS'
}

/**
 * 항목별 멱등 키 장부. 응답을 못 받은 요청의 키만 남겨 다음 요청이 같은 키로 다시 보내고(서버가 처음 응답을 돌려줘
 * 한 번만 차감), 성공하거나 확정 거절이면 지워 다음 요청은 새 키로 보낸다. 방 소품은 같은 항목을 여러 번 사므로
 * 성공 뒤에도 키를 남기면 두 번째 구매가 첫 응답으로 돌아온다(#705).
 */
export function createIdempotencyKeys(newKey: () => string = () => crypto.randomUUID()) {
  const pending = new Map<string, string>()
  return {
    /** 남은 키가 있으면 그 키(재요청), 없으면 새 키 */
    take(itemKey: string) {
      let key = pending.get(itemKey)
      if (!key) { key = newKey(); pending.set(itemKey, key) }
      return key
    },
    /** 요청이 끝난 뒤 부른다. 성공(error 없음)·확정 거절이면 키를 지운다. 그 사이 다른 키가 들어왔으면 건드리지 않는다 */
    settle(itemKey: string, key: string, error?: unknown) {
      if (pending.get(itemKey) !== key) return
      if (error === undefined || !keepIdempotencyKey(error)) pending.delete(itemKey)
    },
    /** 시험·디버그용: 지금 남아 있는 키 */
    peek: (itemKey: string) => pending.get(itemKey),
  }
}
/** 방 소품을 한 개 더 살 수 있는지(판매 중이고 보유 상한 전). 잔액은 따로 본다 */
export const canBuyMore = (item: LookItem | undefined) =>
  !!item && item.slot === 'DECOR' && item.onSale && (item.ownedCount ?? 0) < DECOR_MAX_OWNED
/** 서버 아이템 이름 대신 화면 이름을 쓴다: 동행 캐릭터는 뭉치 친구 이름(#648) */
export const itemName = (item: LookItem) => {
  const friend = item.slot === 'COMPANION' && FRIENDS.find((f) => companionKey(f.companion) === item.itemKey)
  return friend ? friend.name : item.name
}

/**
 * 꾸미기·뭉치 친구들이 같이 쓰는 고르기·해금 상태 (API 명세 2.10·3.12, P22).
 * 호수·뭉치는 처음부터 열려 있고, 나머지는 포인트로 한 번 해금하면 계속 쓸 수 있다(되돌리기·환급 없음).
 * #389의 해금 확정 응답과 소유 목록을 기준으로 선택·착용한다. 해금은 확인 단계를 거치고, 응답 유실 뒤에도 같은 항목은 같은 멱등 키로 다시 보낸다.
 * 방 소품(#704 `DECOR`)은 해금 대신 확인 뒤 한 개씩 산다(`startPurchase`·`confirmPurchase`). 사기마다 새 멱등 키를 쓰고
 * 응답을 못 받았을 때만 같은 키로 다시 보낸다. 해금·사기 모두 확정 4xx 뒤에는 키를 버린다(`keepIdempotencyKey`).
 */
export function useLookShop(child: Child) {
  const { t, companion } = useLook()
  const save = useSaveLook(child.id)
  const settings = useStudentLook(child.id)
  const look = settings.data
  const items = useLookItems(child.id)
  const points = useMyPoints(child.id)
  const unlock = useUnlock(child.id)
  const purchase = usePurchaseDecor(child.id)
  const [confirming, setConfirming] = useState<string | null>(null)
  const unlockKeys = useRef(createIdempotencyKeys())
  const purchaseKeys = useRef(createIdempotencyKeys())
  const catalog = items.error ? undefined : items.data
  const equipped: Equipped = look?.equipped ?? NO_EQUIPPED
  // 미리보기는 지금 고른 착용 그대로(#455). 그림 파일이 없으면 기본 모습
  const worn = wornAssets(equipped, catalog)
  const balance = !points.error ? points.data?.balance : undefined
  const busy = save.isPending || unlock.isPending || purchase.isPending
  const choosingBlocked = busy || settings.isPending || settings.isError || confirming !== null
  const pendingItem = catalog?.find((i) => i.itemKey === confirming)
  const affordable = !!pendingItem && balance !== undefined && balance >= pendingItem.pricePoints
  const choose = (next: { theme?: ThemeId; companion?: CompanionId; equipped?: Equipped }) => {
    if (choosingBlocked) return
    unlock.reset() // 고르는 순간에는 저장 상태만 보이게 한다.
    purchase.reset()
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
  const startUnlock = (itemKey: string) => { save.reset(); unlock.reset(); purchase.reset(); setConfirming(itemKey) }
  /** 방 소품 사기 확인 열기(해금과 같은 확인 상태 `confirming`을 쓴다) */
  const startPurchase = startUnlock
  const cancelUnlock = () => { setConfirming(null); unlock.reset(); purchase.reset() }
  /** 응답 유실 뒤에도 같은 항목은 같은 키로 재전송한다. 확정 4xx면 키를 버려 다음 해금은 새 키로 보낸다. */
  function confirmUnlock() {
    if (!pendingItem || !affordable || busy || !pendingItem.onSale || pendingItem.unlocked || pendingItem.slot === 'DECOR') return
    const itemKey = pendingItem.itemKey
    const key = unlockKeys.current.take(itemKey)
    unlock.mutate({ itemKey, key }, {
      onSuccess: () => {
        unlockKeys.current.settle(itemKey, key)
        setConfirming(null)
      },
      onError: (error) => unlockKeys.current.settle(itemKey, key, error),
    })
  }
  /** 방 소품 한 개 사기. 사기마다 새 키, 응답을 못 받은 경우에만 같은 키로 다시 보낸다(같은 구매로 한 번만 차감). */
  function confirmPurchase() {
    if (!affordable || busy || !canBuyMore(pendingItem)) return
    const itemKey = pendingItem!.itemKey
    const key = purchaseKeys.current.take(itemKey)
    purchase.mutate({ itemKey, key }, {
      onSuccess: () => {
        purchaseKeys.current.settle(itemKey, key)
        setConfirming(null)
      },
      onError: (error) => purchaseKeys.current.settle(itemKey, key, error),
    })
  }
  return {
    t, companion, look, settings, items, points, save, unlock, purchase, catalog, equipped, worn, balance, busy, choosingBlocked,
    confirming, pendingItem, affordable, choose, locked, price, onSale, startUnlock, cancelUnlock, confirmUnlock,
    startPurchase, confirmPurchase,
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

