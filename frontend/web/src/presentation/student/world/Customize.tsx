import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowLeft } from 'lucide-react'
import type { Child } from '../../../domain/classroom.ts'
import { companionToFriend, friendById, FRIENDS, THEMES } from '../../../domain/studentLook.ts'
import type { FriendId, ThemeId } from '../../../domain/studentLook.ts'
import { companionKey, FURNITURE_SLOTS, ITEM_SLOTS, SLOT_LABELS, themeKey, wornAssets } from '../../../domain/retention.ts'
import type { CharacterSlot, FurnitureSlot, ItemSlot, LookItem } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import type { FriendView } from './friendArt.ts'
import { ThemeSwatch } from './ThemeArt.tsx'
import { furnitureSkinName, ROOM_SET_PARTS, wallpaperOf } from './roomAssets.ts'
import type { RoomSlot } from './roomAssets.ts'
import { FurnitureThumb } from './FurnitureThumb.tsx'
import { RoomScene } from './RoomScene.tsx'
import { BUDDY_WIDTH, SCENE } from './homeScene.ts'
import { useGlow } from './roomGlow.ts'
import { CUSTOMIZE_TABS, itemName, THEME_FRAME, unlockMessage, useLookShop } from './lookShop.ts'
import type { CustomizeTab, LookShop } from './lookShop.ts'
import './retention.css'

/** 꾸미기 해금 확인(#389). 확인을 누르기 전에는 요청을 보내지 않는다 */
export function UnlockConfirm({ shop }: { shop: LookShop }) {
  const { confirming, pendingItem, balance, affordable, busy, unlock } = shop
  const ref = useRef<HTMLElement>(null)
  useEffect(() => { if (confirming) ref.current?.focus() }, [confirming])
  if (!confirming) return null
  return (
    <section ref={ref} tabIndex={-1} className="st-unlock-confirm" aria-label="꾸미기 해금 확인">
      <h3>{pendingItem ? itemName(pendingItem) : '꾸미기'} 해금할까요?</h3>
      {pendingItem && balance !== undefined && <p>{pendingItem.pricePoints.toLocaleString('ko-KR')}포인트를 써요.
        {affordable ? ` 해금 후 ${Math.max(0, balance - pendingItem.pricePoints).toLocaleString('ko-KR')}포인트가 남아요.`
          : ` ${Math.max(0, pendingItem.pricePoints - balance).toLocaleString('ko-KR')}포인트가 더 필요해요.`}</p>}
      <p className="st-meta">한 번 열면 계속 쓸 수 있어요. 쓴 포인트는 돌려받을 수 없어요.</p>
      <div className="st-custom-actions">
        <button type="button" className="st-button" disabled={busy} onClick={shop.cancelUnlock}>취소</button>
        <button type="button" className="st-button st-primary" disabled={busy || !affordable || !pendingItem?.onSale || pendingItem?.unlocked}
          onClick={shop.confirmUnlock}>{unlock.isPending ? '해금하는 중이에요' : '포인트로 해금하기'}</button>
      </div>
    </section>
  )
}

/** 저장·해금 결과 한 줄과 오류 */
export function LookStatus({ shop }: { shop: LookShop }) {
  const { unlock, save } = shop
  return (
    <>
      <p className="st-meta st-look-status" role="status">
        {unlock.isPending
          ? '해금하는 중이에요.'
          : unlock.isSuccess
            ? '해금했어요! 이제 골라서 쓸 수 있어요.'
            : save.isPending
              ? '저장하는 중이에요.'
              : save.isSuccess
                ? '골랐어요!'
                : save.isError
                  ? '저장하지 못해서 전에 고른 모습으로 돌아갔어요. 잠시 뒤에 다시 골라 주세요.'
                  : ''}
      </p>
      {unlock.isError && (unlockMessage(unlock.error) ? <p role="alert">{unlockMessage(unlock.error)}</p> : <ErrorNotice error={unlock.error} />)}
      {unlockMessage(save.error) ? <p role="alert">{unlockMessage(save.error)}</p> : <ErrorNotice error={save.error} />}
    </>
  )
}

/** 목록·설정·포인트를 못 읽었을 때 안내 */
export function LookLoadState({ shop }: { shop: LookShop }) {
  const { points, items, settings } = shop
  return (
    <>
      <ErrorNotice error={points.error} retry={() => void points.refetch()} />
      <ErrorNotice error={items.error} retry={() => void items.refetch()} />
      <ErrorNotice error={settings.error} retry={() => void settings.refetch()} />
      {items.isPending && <p role="status">열린 꾸미기를 확인하고 있어요.</p>}
      {items.isError && <p className="st-meta">잠시 뒤에 다시 해 볼까요?</p>}
    </>
  )
}

const won = (n: number) => n.toLocaleString('ko-KR')
const VIEWS: { id: FriendView; label: string }[] = [{ id: 'front', label: '앞' }, { id: 'side', label: '옆' }, { id: 'back', label: '뒤' }]
/** 착용 칸 "안 쓰기" 이름 */
const NONE_LABEL: Record<CharacterSlot, string> = { HAT: '안 쓰기', OUTFIT: '안 입기', ACCESSORY: '없음', BACKGROUND: `${wallpaperOf(null).name} (기본)` }
/** 옷 입히기는 모자·옷·소품(시안 Customize), 배경(= 내 방 벽지)은 내 방 가구 탭으로(2026-11-16) */
const WEAR_SLOTS: ItemSlot[] = ['HAT', 'OUTFIT', 'ACCESSORY']
const ROOM_SLOTS: ItemSlot[] = ['BACKGROUND', ...FURNITURE_SLOTS]
const slotLabel = (slot: ItemSlot) => (slot === 'BACKGROUND' ? '벽지' : SLOT_LABELS[slot])
/** 미리 보기 방 설명용 이름(목록에 없으면 기본 이름) */
const roomItemName = (shop: LookShop, slot: RoomSlot, key: string | null) => {
  const item = key ? shop.catalog?.find((i) => i.itemKey === key) : undefined
  if (item) return itemName(item)
  return slot === 'BACKGROUND' ? `${wallpaperOf(null).name}` : furnitureSkinName(slot, null)
}
const isRoomSlot = (slot: ItemSlot): slot is RoomSlot => (ROOM_SLOTS as ItemSlot[]).includes(slot)

/**
 * 꾸미기 화면에서 고르는 중인 것(미리 보기). 시안 Customize대로 카드를 누르면 왼쪽 미리 보기만 바뀌고,
 * 아래 버튼("이 테마 쓰기"·"함께 다니기"·"이대로 입기"·"N포인트로 열기")을 눌러야 저장·해금한다.
 * 고르지 않은 칸은 지금 쓰는 값을 따른다.
 */
function usePicks(shop: LookShop) {
  const [theme, setTheme] = useState<ThemeId | null>(null)
  const [friend, setFriend] = useState<FriendId | null>(null)
  const [items, setItems] = useState<Partial<Record<ItemSlot, string | null>>>({})
  const item = (slot: ItemSlot) => (slot in items ? items[slot] ?? null : shop.equipped[slot] ?? null)
  const leaveConfirm = () => { if (shop.confirming) shop.cancelUnlock() }
  const { glow, flash } = useGlow()
  const [last, setLast] = useState<RoomSlot | null>(null)
  const assetOf = (key: string | null) => (key && shop.catalog?.find((i) => i.itemKey === key)?.assetKey) || null
  return {
    theme: theme ?? shop.t.id,
    friend: friend ?? companionToFriend(shop.companion),
    item,
    pickTheme: (id: ThemeId) => { leaveConfirm(); setTheme(id) },
    pickFriend: (id: FriendId) => { leaveConfirm(); setFriend(id) },
    pickItem: (slot: ItemSlot, key: string | null) => { leaveConfirm(); setItems((before) => ({ ...before, [slot]: key })); if (isRoomSlot(slot)) { flash(slot); setLast(slot) } },
    /** 방금 고른 내 방 칸(미리 보기 방에서 그 가구만 잠깐 반짝임) */
    glow,
    /** 마지막으로 고른 내 방 칸(미리 보기 아래 "무엇이 바뀌는지" 한 줄) */
    last,
    /** 미리 보기 방 그림(고르는 중인 벽지·가구, 아직 안 연 것도) */
    room: { wallpaper: assetOf(item('BACKGROUND')), desk: assetOf(item('DESK')), wall: assetOf(item('WALL')), wardrobe: assetOf(item('WARDROBE')) },
    /** 미리 보기 캐릭터가 입은 그림(옷 입히기 탭에서 고른 것까지) */
    worn: wornAssets({ ...shop.equipped, ...Object.fromEntries(ITEM_SLOTS.map((s) => [s, item(s)])) }, shop.catalog),
  }
}
type Picks = ReturnType<typeof usePicks>

type Action = { title: string; note: string; label: string; ready: boolean; using: boolean; run?: () => void }

/** 아래 버튼 하나: 고른 것을 쓰거나(저장), 아직 안 열었으면 해금 확인을 연다 */
function tabAction(shop: LookShop, picks: Picks, tab: CustomizeTab): Action {
  const { locked, price, onSale, choose, choosingBlocked, busy, confirming, balance, catalog } = shop
  const canUnlock = !busy && confirming === null && balance !== undefined
  const unlockOr = (key: string, label: string): Pick<Action, 'label' | 'ready' | 'run'> =>
    onSale(key) ? { label, ready: canUnlock, run: () => shop.startUnlock(key) }
      : { label: catalog ? '지금은 열 수 없어요' : '해금 확인 필요', ready: false }
  if (tab === 'theme') {
    const th = THEMES[picks.theme]
    const key = themeKey(th.id)
    if (th.id === shop.t.id) return { title: th.title, note: '지금 쓰고 있는 화면 테마예요.', label: '쓰는 중', ready: false, using: true }
    if (!locked(key)) return { title: th.title, note: '가지고 있어요. 바로 바꿀 수 있어요.', label: '이 테마 쓰기', ready: !choosingBlocked, using: false, run: () => choose({ theme: th.id }) }
    return { title: th.title, note: '미리 보는 중이에요.', using: false, ...unlockOr(key, `${won(price(key))}포인트로 열기`) }
  }
  if (tab === 'friend') {
    const f = friendById(picks.friend)
    const c = f.companion
    if (c === shop.companion) return { title: f.name, note: '함께 다니는 중이에요. 홈과 내 방에 나와요.', label: '함께 다니는 중', ready: false, using: true }
    const key = companionKey(c)
    if (!locked(key)) return { title: f.name, note: '가지고 있어요.', label: '함께 다니기', ready: !choosingBlocked, using: false, run: () => choose({ companion: c }) }
    return { title: f.name, note: '새 친구를 만나 볼까?', using: false, ...unlockOr(key, `${won(price(key))}포인트로 만나기`) }
  }
  // 옷 입히기·내 방 가구: 칸마다 고른 것을 모아 한 번에 입힌다. 아직 안 연 것이 있으면 하나씩 해금부터
  const slots: ItemSlot[] = tab === 'wear' ? WEAR_SLOTS : ROOM_SLOTS
  const [word, subject, is] = tab === 'wear' ? ['옷', '옷이', '옷이에요'] : ['가구', '가구가', '가구예요']
  const title = tab === 'wear' ? '입혀 보는 중' : '내 방 가구'
  const lockedKeys = slots.map(picks.item).filter((k): k is string => !!k && locked(k))
  if (lockedKeys.length) {
    const first = catalog?.find((i) => i.itemKey === lockedKeys[0])
    return { title, note: `아직 안 연 ${subject} ${lockedKeys.length}개 있어요.`, using: false,
      ...unlockOr(lockedKeys[0], `${first ? itemName(first) : word} ${won(price(lockedKeys[0]))}포인트로 열기`) }
  }
  const same = slots.every((s) => picks.item(s) === (shop.equipped[s] ?? null))
  if (same) return { title, note: `모두 가지고 있는 ${is}.`, label: tab === 'wear' ? '입고 있어요' : '쓰는 중', ready: false, using: true }
  return { title, note: `모두 가지고 있는 ${is}.`, label: tab === 'wear' ? '이대로 입기' : '이 가구로 바꾸기', ready: !choosingBlocked, using: false,
    run: () => choose({ equipped: { ...shop.equipped, ...Object.fromEntries(slots.map((s) => [s, picks.item(s)])) } }) }
}

/** 고르기 탭 하나의 내용(카드를 누르면 미리 보기만 바뀐다) */
function TabContent({ shop, picks, tab }: { shop: LookShop; picks: Picks; tab: CustomizeTab }) {
  const { t, companion, catalog, locked, price } = shop
  // 옷 입히기·내 방 가구는 칸(모자·옷·소품 / 벽지·책상·추억의 벽·옷장)을 하나씩 골라 본다(사용자 의견 2026-11-16 "너무 밑에 스크롤해야 하는 거야")
  const [group, setGroup] = useState<ItemSlot | null>(null)
  const lockText = (itemKey: string) => (catalog?.some((i) => i.itemKey === itemKey) ? `${won(price(itemKey))}포인트` : '해금 확인 필요')
  const slotItems = (slot: ItemSlot): LookItem[] => (catalog ?? []).filter((i) => i.slot === slot)

  if (tab === 'theme')
    return (
      <div className="st-pick-grid st-pick-themes">
        {Object.values(THEMES).map((th) => {
          const key = themeKey(th.id)
          const own = !locked(key)
          return (
            <button key={th.id} type="button" className="st-pick st-pick-theme" aria-pressed={th.id === picks.theme}
              disabled={!own && !catalog} onClick={() => picks.pickTheme(th.id)}>
              <ThemeSwatch t={th} />
              {/* 카드 이름·설명은 시안 Customize대로 "생각 호수 · 생각이 뭉치는 호수"(점검 2026-11-15) */}
              <strong>{th.title}</strong>
              <small>{th.sub}</small>
              <span className="st-pick-pill" data-kind={th.id === t.id ? 'using' : own ? 'owned' : 'locked'}>
                {th.id === t.id ? '쓰는 중' : own ? '가지고 있어요' : lockText(key)}
              </span>
            </button>
          )
        })}
      </div>
    )
  if (tab === 'friend')
    // 뭉치 친구들 12종(#648). core가 12종을 모두 저장해(#697) 모두 고르고 해금한다(#698)
    return (
      <div className="st-pick-grid st-pick-friends">
        {FRIENDS.map((f) => {
          const c = f.companion
          const style = { '--st-friend-tint': f.color } as CSSProperties
          const own = !locked(companionKey(c))
          const kind = c === companion ? 'using' : own ? 'owned' : 'locked'
          return (
            <button key={f.id} type="button" className="st-pick st-pick-buddy st-pick-friend" style={style}
              aria-pressed={picks.friend === f.id} disabled={!own && !catalog} onClick={() => picks.pickFriend(f.id)}>
              <Companion friend={f.id} size={86} decorative />
              <strong>{f.name}</strong>
              <span className="st-pick-pill" data-kind={kind}>
                {c === companion ? '함께 다니는 중' : own ? '가지고 있어요' : lockText(companionKey(c))}
              </span>
            </button>
          )
        })}
      </div>
    )
  const tile = (slot: ItemSlot, item: LookItem | null) => {
    const key = item?.itemKey ?? null
    const lockedItem = !!item && !item.unlocked
    const name = item ? itemName(item) : slot in NONE_LABEL ? NONE_LABEL[slot as CharacterSlot] : `${furnitureSkinName(slot as FurnitureSlot, null)} (기본)`
    const using = (shop.equipped[slot] ?? null) === key
    const status = lockedItem ? (item.onSale ? `${won(item.pricePoints)}포인트` : '지금은 열 수 없어요')
      : tab === 'furniture' ? (using ? '쓰는 중' : '가지고 있어요') : item ? '가지고 있어요' : ''
    return (
      <button key={`${slot}:${key ?? 'none'}`} type="button" className={`st-pick-tile${tab === 'furniture' ? ' st-pick-furniture' : ''}`}
        aria-pressed={picks.item(slot) === key} disabled={lockedItem && (!item.onSale || !catalog)} onClick={() => picks.pickItem(slot, key)}>
        {tab === 'furniture' ? (
          <span className="st-tile-art st-tile-room"><FurnitureThumb slot={slot as RoomSlot} assetKey={item?.assetKey} /></span>
        ) : (
          <span className="st-tile-art" aria-hidden="true">
            <Companion friend={picks.friend} size={64} decorative worn={item?.assetKey ? { [slot]: item.assetKey } : {}} />
          </span>
        )}
        <strong>{name}</strong>
        {/* 함께 바뀌는 것(세트)을 칸마다 적는다 */}
        {tab === 'furniture' && <small>{ROOM_SET_PARTS[slot as RoomSlot]}</small>}
        {status && <span className="st-pick-pill" data-kind={lockedItem ? 'locked' : using ? 'using' : 'owned'}>{status}</span>}
      </button>
    )
  }
  const slots: ItemSlot[] = tab === 'wear' ? WEAR_SLOTS : ROOM_SLOTS
  // 내 방 가구 스킨(P27): 기본 스킨은 착용 칸이 빈 상태라 목록에 아이템이 없어도 고를 수 있다
  if (!slots.some((s) => slotItems(s).length > 0))
    return <p className="st-empty">{tab === 'wear' ? '아직 입혀 볼 옷이 없어요. 곧 새 옷이 들어와요.' : '아직 바꿀 수 있는 가구가 없어요.'}</p>
  const groupSlots = slots.filter((s) => tab !== 'wear' || slotItems(s).length > 0)
  const shown = group && groupSlots.includes(group) ? group : groupSlots[0]
  return (
    <div className="st-pick-groups">
      <div className="st-pick-slotbar" role="group" aria-label={tab === 'wear' ? '입혀 볼 곳' : '바꿀 것'}>
        {groupSlots.map((s) => (
          <button key={s} type="button" aria-pressed={s === shown} onClick={() => setGroup(s)}>
            {slotLabel(s)}
            {picks.item(s) !== (shop.equipped[s] ?? null) && <i aria-label="고른 것 있음" />}
          </button>
        ))}
      </div>
      <div className="st-pick-group" role="group" aria-label={slotLabel(shown)}>
        <div className="st-pick-tiles">{[null, ...slotItems(shown)].map((item) => tile(shown, item))}</div>
      </div>
    </div>
  )
}

/** 탭 줄 + 고르기 영역 + 아래 버튼(꾸미기 화면 오른쪽). 탭은 WAI-ARIA 탭 패턴(좌우 화살표로 이동) */
function CustomizeTabs({ shop, picks, tab, onTab }: { shop: LookShop; picks: Picks; tab: CustomizeTab; onTab: (tab: CustomizeTab) => void }) {
  const current = CUSTOMIZE_TABS.find((x) => x.id === tab)!
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const move = (dir: number) => {
    const i = CUSTOMIZE_TABS.findIndex((x) => x.id === tab)
    const next = CUSTOMIZE_TABS[(i + dir + CUSTOMIZE_TABS.length) % CUSTOMIZE_TABS.length].id
    onTab(next)
    tabRefs.current[next]?.focus()
  }
  const action = tabAction(shop, picks, tab)
  return (
    <>
      <div className="st-custom-tabbar">
        <div className="st-custom-tabs" role="tablist" aria-label="꾸미기 종류">
          {CUSTOMIZE_TABS.map((x) => (
            <button key={x.id} ref={(el) => { tabRefs.current[x.id] = el }} type="button" role="tab" id={`custom-tab-${x.id}`}
              aria-selected={x.id === tab} aria-controls="custom-panel" tabIndex={x.id === tab ? 0 : -1}
              onClick={() => onTab(x.id)}
              onKeyDown={(e) => { if (e.key === 'ArrowRight') move(1); else if (e.key === 'ArrowLeft') move(-1) }}>
              {x.label}
            </button>
          ))}
        </div>
        <p className="st-points-pill" role="status">{shop.balance !== undefined ? `내 포인트 ${won(shop.balance)}`
          : shop.points.isPending ? '포인트를 확인하고 있어요.' : '포인트를 확인하지 못했어요.'}</p>
      </div>
      <LookLoadState shop={shop} />
      <div id="custom-panel" role="tabpanel" className="st-custom-panel" aria-labelledby={`custom-tab-${tab}`}>
        <section aria-labelledby={`pick-${tab}`} className="st-custom-list">
          <h2 className="st-custom-question" id={`pick-${tab}`}>{current.question}</h2>
          <TabContent shop={shop} picks={picks} tab={tab} />
        </section>
      </div>
      <div className="st-custom-action">
        <span><b>{action.title}</b><small>{action.note}</small></span>
        <button type="button" className="st-custom-go" data-using={action.using} disabled={!action.ready} onClick={action.run}>{action.label}</button>
      </div>
      <UnlockConfirm shop={shop} />
      {!shop.confirming && <p className="st-meta st-custom-note">한 번 열면 계속 쓸 수 있어요. 쓴 포인트는 돌려받을 수 없어요.</p>}
      <LookStatus shop={shop} />
    </>
  )
}

/** 왼쪽 미리 보기: 화면 테마 탭은 작은 홈(우리 집 그림 + 캐릭터), 캐릭터·옷 탭은 캐릭터 무대, 가구 탭은 작은 내 방 */
function Preview({ shop, picks, tab, onRoom }: { shop: LookShop; picks: Picks; tab: CustomizeTab; onRoom: () => void }) {
  const th = THEMES[picks.theme]
  const frame = { '--st-preview-frame': THEME_FRAME[th.id], '--st-preview-top': th.top } as CSSProperties
  if (tab === 'theme')
    return (
      <>
        <div className="st-custom-preview-box st-preview-home" style={frame}>
          <div className="st-preview-paper">
            <p className="st-preview-head"><b>{th.sub}</b><span><em>홈</em><i>내 방</i></span></p>
            {/* 홈 장면과 같은 틀(3:2)·그림(10:8)·자리·비율(homeScene.ts): 캐릭터가 테마마다 발판 가운데에 선다 */}
            <div className="st-preview-scene">
              <div className="st-preview-art">
                <img src={`/student-assets/home/${th.id}.jpg`} alt="" />
                <span className="st-preview-buddy" style={{ left: `${SCENE[th.id].cx - BUDDY_WIDTH / 2}%`, bottom: `${SCENE[th.id].cb}%`, width: `${BUDDY_WIDTH}%` }}>
                  <Companion kind={shop.companion} size={110} decorative worn={shop.worn} />
                </span>
              </div>
            </div>
          </div>
        </div>
        <p className="st-meta">이 테마를 쓰면 바깥 테두리와 홈 그림이 같이 바뀌어요.</p>
      </>
    )
  if (tab === 'furniture') {
    // 시안의 "가구는 내 방에서 바로 바꿔요" 안내 카드 대신 작은 내 방(사용자 결정 2026-11-16 "뭐가 어떻게 변하는지 보여야지").
    // 칸을 누르면 이 방에서 먼저 바뀌고 바뀐 가구가 잠깐 반짝인다. 아직 안 연 가구도 미리 볼 수 있다
    const last = picks.last
    return (
      <>
        <div className="st-custom-preview-box st-preview-roombox" style={frame}>
          <RoomScene look={picks.room} glow={picks.glow} companion={shop.companion} worn={shop.worn}
            label={`고르는 중인 내 방: ${(['BACKGROUND', ...FURNITURE_SLOTS] as RoomSlot[]).map((s) => `${slotLabel(s)} ${roomItemName(shop, s, picks.item(s))}`).join(', ')}`} />
        </div>
        <p className="st-meta st-preview-room-note">
          {last ? <><b>{ROOM_SET_PARTS[last]}</b>{last === 'WALL' ? '가' : '이'} 바뀌어요.</> : '칸을 누르면 이 방에서 먼저 볼 수 있어요.'}
          {' '}<button type="button" className="st-link-inline" onClick={onRoom}>내 방으로 가기 →</button>
        </p>
      </>
    )
  }
  const f = friendById(picks.friend)
  return <StagePreview frame={frame} friend={f} worn={picks.worn} />
}

/** 캐릭터 무대 + 돌려 보기(앞·옆·뒤, 착용 그림은 앞모습에서만 보임) */
function StagePreview({ frame, friend: f, worn }: { frame: CSSProperties; friend: ReturnType<typeof friendById>; worn: Picks['worn'] }) {
  const [view, setView] = useState<FriendView>('front')
  return (
    <>
      <div className="st-custom-preview-box st-preview-stage" style={frame}>
        <span className="st-preview-name">{f.name}</span>
        <span className="st-preview-ground" aria-hidden="true" />
        <span className="st-preview-big"><Companion friend={f.id} size={240} decorative worn={worn} view={view} /></span>
        <span className="st-preview-turn" role="group" aria-label="돌려 보기">
          {VIEWS.map((v) => <button key={v.id} type="button" aria-pressed={view === v.id} onClick={() => setView(v.id)}>{v.label}</button>)}
        </span>
      </div>
      <p className="st-meta">{f.desc}</p>
    </>
  )
}

/**
 * 꾸미기 화면(/student/customize?tab=, #648 시안 Customize, URL 기준안). 학생 틀 안 전체 화면이고
 * 왼쪽 미리 보기 + 오른쪽 탭 4개(화면 테마·캐릭터·옷 입히기·내 방 가구) + 아래 버튼.
 * 카드는 미리 보기만 바꾸고, 아래 버튼이 저장(PUT 설정)·해금(확인 단계 → POST 해금, 멱등 키)을 한다. 요청은 예전 꾸미기 창과 같다.
 */
export function StudentCustomize({ child, tab, onTab, onBack }: {
  child: Child
  tab: CustomizeTab
  onTab: (tab: CustomizeTab) => void
  onBack: () => void
}) {
  return <CustomizePage key={child.id} child={child} tab={tab} onTab={onTab} onBack={onBack} />
}
function CustomizePage({ child, tab, onTab, onBack }: { child: Child; tab: CustomizeTab; onTab: (tab: CustomizeTab) => void; onBack: () => void }) {
  const shop = useLookShop(child)
  const picks = usePicks(shop)
  return (
    <main className="st-paper st-sheet st-custom-page" aria-busy={shop.busy}>
      <section className="st-custom-left" aria-label="미리 보기">
        <button type="button" className="st-pill-back" onClick={onBack}><ArrowLeft aria-hidden="true" /> 내 방</button>
        <h1 className="st-title-mix"><span>나만의 </span>꾸미기</h1>
        <Preview shop={shop} picks={picks} tab={tab} onRoom={onBack} />
      </section>
      <section className="st-custom-right" aria-label="꾸미기 고르기">
        <CustomizeTabs shop={shop} picks={picks} tab={tab} onTab={onTab} />
      </section>
    </main>
  )
}
