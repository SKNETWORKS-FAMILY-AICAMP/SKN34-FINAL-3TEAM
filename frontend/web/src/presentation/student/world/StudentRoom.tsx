import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { RotateCcw, RotateCw, X } from 'lucide-react'
import { useSaveLook, useStudentLook } from '../../../data/studentLook/queries.ts'
import { useAlbum, useDecorSpots, useFrameSlots, useLookItems, useMarkFramesSeen, useSaveDecorSpots, useSaveFrameSlots, useWeeklyTheme } from '../../../data/retention/queries.ts'
import { blockedByDecor, cellPlane, cellsOf, cellSpan, decorCenter, decorFaces, decorFloorBlocks, drawableDecor, firstPlace, placeableCells, placeProblem, stepCell } from './decorArt.ts'
import { RoomPanArrows } from './RoomPanArrows.tsx'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { DECOR_MAX_OWNED, DECOR_SPOT_LIMIT, episodeKey, FRAME_SLOT_COUNT, FURNITURE_SLOTS, NO_EQUIPPED, SLOT_LABELS, weekLabel } from '../../../domain/retention.ts'
import type { AlbumItem, DecorSurface, FrameSlot, FurnitureSlot, LookItem } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { SpeechBubble } from './SpeechBubble.tsx'
import { boardTagTransform, WORLD_TOP, DESK_Z, faceStyle, MAT_RADIUS, MATS, ROOM, roomFaces, SHELF, slotTransform, WARDROBE } from './roomArt.ts'
import { CAN_ROTATE, CAN_WALK, clamp, useRoomWalk } from './useRoomWalk.ts'
import type { MatId } from './roomArt.ts'
import { decorPlaceText, floorName, furnitureSkinName, ROOM_SET_PARTS, skinOf, wallpaperOf } from './roomAssets.ts'
import type { RoomSlot } from './roomAssets.ts'
import { DecorThumb, FurnitureThumb } from './FurnitureThumb.tsx'
import { decorColor, decorColors } from './decorDraw.ts'
import { FrameScene } from './FrameScene.tsx'
import { glowClass, useGlow } from './roomGlow.ts'
import { canBuyMore, unlockMessage, useLookShop } from './lookShop.ts'
import { josa } from './themeWeek.ts'
import type { CustomizeTab } from './lookShop.ts'
import { UnlockConfirm } from './Customize.tsx'
import { useLook } from './lookContext.ts'
import './room.css'

type Placed = { slotNo: number; themeId: string; weekStart: string; title: string; imageUrl: string | null }
/** 내 방에서 바꾸는 착용 칸: 벽지(배경 아이템)와 가구 3종 */
type RoomTab = 'frames' | 'wallpaper' | 'floor' | 'furniture' | 'decor'
const ROOM_TABS: { id: RoomTab; label: string; hint: string }[] = [
  { id: 'frames', label: '액자 걸기', hint: '빈 자리를 눌러 기념 액자를 걸어요.' },
  { id: 'wallpaper', label: '벽지', hint: '벽지·커튼이 같이 바뀌어요. 바닥을 따로 안 골랐으면 바닥도 같이 바뀌어요. 안 연 것도 눌러서 바로 열 수 있어요.' },
  { id: 'floor', label: '바닥', hint: '바닥만 바뀌어요. 기본은 벽지와 같이 바뀌는 바닥이에요. 안 연 것도 눌러서 바로 열 수 있어요.' },
  { id: 'furniture', label: '가구', hint: '책상·책장, 추억의 벽·액자, 옷장·문이 같이 바뀌어요. 안 연 것도 눌러서 바로 열 수 있어요.' },
  // 놓기는 core #723(바닥·벽 칸) 뒤에 이 탭에 붙인다. 지금은 사기만
  { id: 'decor', label: '방 소품', hint: '[놓기]로 방에 놓고 화살표나 초록 칸으로 옮겨요. 같은 것을 여러 개 살 수 있어요(하나에 8개까지).' },
]

/** 착용 itemKey → 그림 assetKey. 목록을 못 받으면 기본 그림 */
const assetOf = (items: LookItem[] | undefined, itemKey: string | null | undefined) =>
  (itemKey && items?.find((i) => i.itemKey === itemKey)?.assetKey) || null
const toPlaced = ({ slotNo, themeId, weekStart, title, imageUrl }: FrameSlot): Placed => ({ slotNo, themeId, weekStart, title, imageUrl })
const sameFrames = (a: Placed[], b: Placed[]) =>
  JSON.stringify(a.map((d) => [d.slotNo, episodeKey(d)]).sort()) === JSON.stringify(b.map((d) => [d.slotNo, episodeKey(d)]).sort())

const frameSaveMessage = (e: unknown) => {
  const code = e instanceof ApiError ? e.problem.code : ''
  if (code === 'THEME_FRAME_NOT_FOUND') return '가지고 있지 않은 액자가 있어요. 앨범을 다시 확인하고 골라 주세요.'
  if (code === 'VALIDATION_FAILED') return '같은 액자를 두 번 걸었거나 자리 번호가 맞지 않아요.'
  return '벽에 걸지 못했어요. 고른 그대로 두었으니 잠시 뒤에 다시 저장해 주세요.'
}
const LOOK_SAVE_FAILED = '벽지·가구를 바꾸지 못했어요. 고른 그대로 두었으니 잠시 뒤에 다시 저장해 주세요.'
const DECOR_SAVE_FAILED = '방 소품을 놓지 못했어요. 놓은 그대로 두었으니 잠시 뒤에 다시 저장해 주세요.'
/** 방 소품 초안 한 칸(서버에 보내는 모양, core #723 칸 + #758 색). color null = 소품 기본 색 */
type DraftDecor = { surface: DecorSurface; col: number; row: number; itemKey: string; color: string | null }
const decorKey = (list: DraftDecor[]) => JSON.stringify(list.map((d) => `${d.surface}:${d.col}:${d.row}:${d.itemKey}:${d.color ?? ''}`).sort())

/** 액자 속 그림이 없을 때 쓰는 작은 풍경. 회차마다 언덕 색만 달라진다 */
function FrameArt({ frame }: { frame: { themeId: string; title?: string; imageUrl: string | null } }) {
  if (frame.imageUrl) return <img src={frame.imageUrl} alt="" />
  // 회차마다 다른 장면(앨범과 같은 FrameScene, 사용자 의견 2026-11-16 "액자도 그림이 너무 일정해")
  return <FrameScene className="st-room-scene" themeId={frame.themeId} title={frame.title} />
}

/**
 * 내 방(/student/room, P27·FN-RET-09, #556·#648). 시안 MyPage의 그림체를 방 안 시점·고정 시점으로 그린다.
 * 사용자 결정 2026-11-16: 가구 = 메뉴. 방 가운데(출발 자리)에서 출발한 뭉치가 바닥을 누르거나 방향키로 걸어가 갈 곳 앞 발판에 서면 말풍선 단추로 간다
 * (책상 → 홈, 창문 → 시작 이야기, 추억의 벽 → 앨범, 옷장 → 옷 입히기·뭉치 친구들, 문 → 친구 생각, 책장 → 내 공책). 가구 이름표를 누르면 걷지 않고 바로 간다.
 * "방 꾸미기"를 누르면 아래 서랍(액자 걸기·벽지·가구)에서 고른 것이 위 방에 바로 보이고, 저장해야 반영된다
 * (액자는 추억의 벽 저장 PUT, 벽지·가구는 착용 저장 PUT). 뭉치 자리는 저장하지 않는다.
 */
export function StudentRoom({ child, onTheme, onAlbum, onCustomize, onFriends, onStory, onJournal, onCommunity }: {
  child: Child
  onTheme: () => void
  onAlbum: () => void
  /** 꾸미기 화면. 옷장은 옷 입히기 탭, "캐릭터·옷 꾸미기"는 캐릭터 탭으로 연다 */
  onCustomize: (tab?: CustomizeTab) => void
  onFriends: () => void
  /** 창문: 이번 주 시작 이야기 다시 보기(없으면 홈) */
  onStory?: () => void
  /** 책장: 내 공책(없으면 숨김) */
  onJournal?: () => void
  /** 문: 친구 생각(사용자 결정 2026-11-16, 없으면 숨김) */
  onCommunity?: () => void
}) {
  const { t, companion, worn } = useLook()
  const look = useStudentLook(child.id)
  const items = useLookItems(child.id)
  const slots = useFrameSlots(child.id)
  const album = useAlbum(child.id, 0, 50)
  const weekly = useWeeklyTheme(child.id)
  const saveFrames = useSaveFrameSlots(child.id)
  const saveLook = useSaveLook(child.id)
  const catalog = items.error ? undefined : items.data
  const equipped = look.data?.equipped ?? NO_EQUIPPED
  const placed = (slots.data ?? []).map(toPlaced)
  const owned = album.data?.items ?? []
  const unseen = owned.filter((i) => !i.seen)
  const markSeen = useMarkFramesSeen(child.id)
  // 새 액자 알림을 닫거나 걸러 가면 확인(seen)을 남긴다 — 예전에는 앨범에 들어가야만 남아 내 방에 올 때마다 알림이 다시 떴음(사용자 결정 2026-11-16)
  const dismissNew = () => { setNewSeen(true); if (unseen.length) markSeen.mutate(unseen.map(({ themeId, weekStart }) => ({ themeId, weekStart }))) }

  // ---- 꾸미기(편집) 상태 ----
  const [editing, setEditing] = useState(false)
  const [tab, setTab] = useState<RoomTab>('frames')
  const [furn, setFurn] = useState<FurnitureSlot>('DESK')
  const [draftFrames, setDraftFrames] = useState<Placed[]>([])
  const [draftLook, setDraftLook] = useState<Partial<Record<RoomSlot, string | null>>>({})
  const [picking, setPicking] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [errors, setErrors] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [newSeen, setNewSeen] = useState(false)
  // 방 소품 놓기 초안(#705): 놓은 칸 목록, 고른(옮기는) 소품 순서, 못 놓는 까닭 한 줄
  const [draftDecor, setDraftDecor] = useState<DraftDecor[]>([])
  const [pickedDecor, setPickedDecor] = useState<number | null>(null)
  const [decorMsg, setDecorMsg] = useState('')
  // 저장·취소 알림은 잠시 보이고 사라진다(화면 읽기 프로그램은 바뀔 때 읽음)
  useEffect(() => {
    if (!note) return
    const id = window.setTimeout(() => setNote(''), 4000)
    return () => clearTimeout(id)
  }, [note])
  // 놓은 방 소품(#705, core #723 계약안): 그릴 수 있는 것만(그림 목록·맞는 면·막힌 칸·겹침 거름). 선 것은 걷기 막힘
  const decorSpots = useDecorSpots(child.id)
  const saveDecor = useSaveDecorSpots(child.id)
  /** 놓은 칸 목록을 받았나. 받기 전에는 방 소품 놓기를 열지 않는다(빈 목록으로 저장하면 놓은 소품이 다 사라짐, 액자 버그와 같은 까닭) */
  const decorReady = decorSpots.isSuccess
  const savedDecor: DraftDecor[] = (decorSpots.data ?? []).map(({ surface, col, row, itemKey, color }) => ({ surface, col, row, itemKey, color }))
  const decorAsset = (itemKey: string) => catalog?.find((i) => i.itemKey === itemKey)?.assetKey ?? decorSpots.data?.find((s) => s.itemKey === itemKey)?.assetKey ?? ''
  const decorNow = (editing && decorReady ? draftDecor : savedDecor).map((d) => ({ ...d, assetKey: decorAsset(d.itemKey) }))
  const shownDecor = drawableDecor(decorNow)
  // 옮기는 방 소품: 칸이 손가락 크기(44px)보다 작으면 방을 키우고 그 소품을 화면 가운데로(#705)
  const movingSpot = editing && tab === 'decor' && decorReady && pickedDecor !== null ? draftDecor[pickedDecor] : undefined
  const movingPlaced = movingSpot ? { ...movingSpot, assetKey: decorAsset(movingSpot.itemKey) } : undefined
  const {
    view, dragging, pos, facing, pose, moving, jumping, stageRef, holderRef, roomRef, drawerRef,
    fit, holderH, worldScale, onKeyDown, onKeyUp, onBlur, onPointerDown, onFloorClick, turn, faceCamera,
    pan, limX, stageTransform, toHolder, panTo,
  } = useRoomWalk({
    paused: editing,
    blocked: blockedByDecor(decorFloorBlocks(shownDecor)),
    fitSpan: movingPlaced ? cellSpan(movingPlaced.surface) : null,
    focus: movingPlaced ? decorCenter(movingPlaced) : null,
  })
  const frames = editing ? draftFrames : placed
  const { glow, flash } = useGlow()
  const wearing = (slot: RoomSlot) => (editing && slot in draftLook ? draftLook[slot] ?? null : equipped[slot] ?? null)
  const framesChanged = editing && !sameFrames(draftFrames, placed)
  // 방 꾸미기 서랍에서 바로 열기(사용자 의견 2026-11-17 "구매를 방 꾸미기에서도 할 수 있게"): 꾸미기 화면과 같은 해금 흐름(lookShop)
  const shop = useLookShop(child)
  /** 아직 안 연 것을 고른 칸이 있나(열지 않은 채 저장하면 서버가 LOOK_LOCKED로 거절) */
  const lockedDraft = editing && (Object.values(draftLook) as (string | null | undefined)[]).some((k) => !!k && catalog?.some((i) => i.itemKey === k && !i.unlocked))
  const lookChanged = editing && (Object.keys(draftLook) as RoomSlot[]).some((s) => (draftLook[s] ?? null) !== (equipped[s] ?? null))
  const decorChanged = editing && decorReady && decorKey(draftDecor) !== decorKey(savedDecor)
  const slotItems = (slot: RoomSlot | 'DECOR') => (catalog ?? []).filter((i) => i.slot === slot)
  const tabs = ROOM_TABS.filter((x) => x.id === 'frames' || (x.id === 'wallpaper' ? slotItems('BACKGROUND').length > 0 : x.id === 'floor' ? slotItems('FLOOR').length > 0 : x.id === 'decor' ? slotItems('DECOR').length > 0 : FURNITURE_SLOTS.some((s) => slotItems(s).length > 0)))

  /** 걸린 액자 목록을 받았나. 받기 전에 방 꾸미기를 열면 빈 목록으로 초안을 만들어, 저장하면 걸린 액자가 모두 내려갔다(#705 기존 버그) */
  const framesReady = slots.isSuccess
  const startEdit = (slotNo: number | null = null) => {
    if (!framesReady) return
    shop.cancelUnlock()
    setDraftFrames(placed)
    setDraftLook({})
    setDraftDecor(savedDecor)
    setPickedDecor(null)
    setDecorMsg('')
    setTab('frames')
    setPicking(slotNo)
    setErrors([])
    setNote('')
    setEditing(true)
  }
  const cancel = () => {
    shop.cancelUnlock()
    setEditing(false)
    setPickedDecor(null)
    setPicking(null)
    setErrors([])
    setNote('바꾼 내용을 취소했어요.')
  }
  const put = (slotNo: number, frame: AlbumItem | null) => {
    setDraftFrames((before) => [
      ...before.filter((d) => d.slotNo !== slotNo && (!frame || episodeKey(d) !== episodeKey(frame))),
      ...(frame ? [{ slotNo, themeId: frame.themeId, weekStart: frame.weekStart, title: frame.title, imageUrl: frame.imageUrl }] : []),
    ].sort((a, b) => a.slotNo - b.slotNo))
    setPicking(null)
    setErrors([])
  }
  /** 저장: 바뀐 것만 보낸다. 하나라도 실패하면 고른 그대로 두고 안내한다(FN-RET-09) */
  const save = async () => {
    if (saving) return
    setSaving(true)
    setErrors([])
    const jobs: Promise<unknown>[] = []
    const kinds: ('frames' | 'look' | 'decor')[] = []
    if (framesChanged) {
      kinds.push('frames')
      jobs.push(saveFrames.mutateAsync(draftFrames.map(({ slotNo, themeId, weekStart }) => ({ slotNo, themeId, weekStart }))))
    }
    if (lookChanged) {
      kinds.push('look')
      jobs.push(saveLook.mutateAsync({ theme: t.id, companion, equipped: { ...equipped, ...draftLook } }))
    }
    if (decorChanged) {
      kinds.push('decor')
      // 색 포함 계약 칸 다섯 개 그대로 보낸다(core #758: 색을 빼면 서버가 기본 색으로 바꿔 저장하므로 늘 함께 보냄)
      jobs.push(saveDecor.mutateAsync(draftDecor))
    }
    const results = await Promise.allSettled(jobs)
    setSaving(false)
    const failed = results.flatMap((r, i) => (r.status === 'rejected' ? [kinds[i] === 'frames' ? frameSaveMessage(r.reason) : kinds[i] === 'decor' ? DECOR_SAVE_FAILED : LOOK_SAVE_FAILED] : []))
    if (failed.length) {
      setErrors(failed)
      return
    }
    setEditing(false)
    setPicking(null)
    setPickedDecor(null)
    setNote(kinds.length === 1 && kinds[0] === 'frames' ? '추억의 벽을 저장했어요.' : '내 방을 저장했어요.')
  }

  /** 뭉치가 올라선 발판(걷는 중이 아닐 때) */
  // 가장 가까운 가구 앞(반지름 안)이면 그 말풍선
  const near = MATS.map((m) => ({ id: m.id, d: Math.hypot(m.x - pos.x, m.z - pos.z) })).filter((m) => m.d < MAT_RADIUS).sort((a, b) => a.d - b.d)[0]
  const onMat: MatId | null = !moving && !editing ? near?.id ?? null : null


  const faces = roomFaces({
    wallpaper: assetOf(catalog, wearing('BACKGROUND')),
    floor: assetOf(catalog, wearing('FLOOR')),
    desk: assetOf(catalog, wearing('DESK')),
    wall: assetOf(catalog, wearing('WALL')),
    wardrobe: assetOf(catalog, wearing('WARDROBE')),
  }, onMat).concat(decorFaces(shownDecor, faceCamera))
  const framing = editing && tab === 'frames'
  const showNew = !editing && !newSeen && unseen.length > 0
  const firstEmpty = Array.from({ length: FRAME_SLOT_COUNT }, (_, i) => i + 1).find((n) => !placed.some((p) => p.slotNo === n)) ?? null
  const pickingFrame = picking !== null ? frames.find((d) => d.slotNo === picking) : undefined
  const thumb = placed[0] ?? owned[0]
  const theme = weekly.data
  const solved = theme ? theme.days.filter((d) => d.attemptStatus === 'COMPLETED').length : 0

  /** 추억의 벽 액자 나무 틀 색(추억의 벽 스킨 세트) */
  const frameWood = skinOf('WALL', assetOf(catalog, wearing('WALL'))).set[0]

  /**
   * 갈 곳 6개(사용자 결정 2026-11-16 ① 가구 = 메뉴): 이름표(누르면 바로)와 발판 말풍선(뭉치가 서면 단추 하나).
   * 이름표는 모두 화면 쪽을 보는 같은 모양(추억의 벽도, #1093 — 예전 게시판 면 이름표는 벽 따라 기울어 보였다).
   */
  // 이름표는 화면 쪽으로 돌아가 있어 오른쪽 위 모서리가 뒤로 들어간다(기본 시점 약 73px, 돌리기를 켜면 끝 시점 ry -50·rx -40에서 약 106px) → 뒷벽에서 110px 넘게 띄움
  // (옷장 이름표가 뒷벽에서 66px라 오른쪽이 벽에 잘리던 것, 사용자 의견 2026-11-16 "이것도 잘린다"). 창문은 왼쪽 벽에서 120px.
  // 그 깊이(z, 창문은 x)를 두고, 기본 시점(ROOM_VIEW)에서 이름표 아래 가운데가 물건 윗면 가운데 10px 위에 오도록 x·y(창문은 z·y)를 맞췄다(#1093, 1280×800 실측 오차 0.5px 안).
  // s: 깊이가 달라 원근으로 커 보이고 작아 보이는 차이를 맞춘 배율(기본 시점 화면 폭이 같게) — 모든 이름표가 같은 글자 크기로 보인다
  const SPOTS: { id: MatId; label: string; tag: { x: number; y: number; z: number; s: number }; say: string; button: string; go?: () => void; more?: { label: string; go: () => void } }[] = [
    { id: 'desk', label: '책상 · 오늘 문제', tag: { x: -451, y: -155, z: DESK_Z + 20, s: 1.079 }, say: '오늘 문제 풀래?', button: '오늘 문제 풀기', go: onTheme },
    { id: 'window', label: '창문 · 이번 주 이야기', tag: { x: -ROOM.W / 2 + 120, y: -482, z: 265, s: 0.988 }, say: '이번 주 이야기 다시 볼까?', button: '이야기 보기', go: onStory ?? onTheme },
    { id: 'board', label: '추억의 벽 · 액자', tag: { x: -7, y: -426, z: -ROOM.D / 2 + 120, s: 1.061 }, say: '액자 볼까?', button: '추억 앨범 열기', go: onAlbum },
    { id: 'wardrobe', label: '옷장 · 옷 갈아입기', tag: { x: 322, y: -411, z: WARDROBE.z + 60, s: 1 }, say: '옷 갈아입을까?', button: '옷 갈아입기', go: () => onCustomize('wear'),
      more: { label: '뭉치 친구 바꾸기', go: onFriends } },
    { id: 'door', label: '문 · 친구 생각', tag: { x: 588, y: -371, z: -ROOM.D / 2 + 120, s: 0.958 }, say: '친구들 생각 보러 갈까?', button: '친구 생각 보기', go: onCommunity },
    { id: 'shelf', label: '책장 · 내 공책', tag: { x: -396, y: -297, z: SHELF.z + 60, s: 1.157 }, say: '내 공책 볼까?', button: '내 공책 열기', go: onJournal },
  ]
  const bubble = onMat ? SPOTS.find((s) => s.id === onMat) : undefined
  const bubbleAt = toHolder(pos.x, -150, pos.z)

  // 액자 고르기 창: 열리면 첫 버튼으로, Esc로 닫으면 그 자리 버튼으로 초점을 돌린다
  const pickerRef = useRef<HTMLDivElement>(null)
  const slotRefs = useRef<Record<number, HTMLButtonElement | null>>({})
  useEffect(() => { if (picking !== null) pickerRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus() }, [picking])
  const closePicker = () => { const n = picking; setPicking(null); if (n !== null) slotRefs.current[n]?.focus() }

  const choice = (slot: RoomSlot, item: LookItem | null) => {
    const key = item?.itemKey ?? null
    const selected = wearing(slot) === key
    const lockedItem = !!item && !item.unlocked
    // 안 연 것도 판매 중이면 눌러서 방에 먼저 보고 바로 열 수 있다(포인트는 열 때 차감, 방에는 저장해야 반영)
    const canOpen = lockedItem && item.onSale && !!catalog
    const name = item ? item.name : slot === 'BACKGROUND' ? `${wallpaperOf(null).name} (기본)` : slot === 'FLOOR' ? `${floorName(null)} (기본)` : `${furnitureSkinName(slot, null)} (기본)`
    return (
      <button key={`${slot}:${key ?? 'none'}`} type="button" className="st-room-choice" aria-pressed={selected} disabled={(lockedItem && !canOpen) || saving || shop.busy}
        onClick={() => {
          setDraftLook((d) => ({ ...d, [slot]: key })); setErrors([]); flash(slot)
          if (canOpen) shop.startUnlock(key!)
          else if (shop.confirming) shop.cancelUnlock()
        }}>
        {/* 색 네모 대신 그 칸이 바꾸는 가구 그림(세트 포함), 아래 줄에 함께 바뀌는 것 */}
        <span className="st-room-swatch"><FurnitureThumb slot={slot} assetKey={item?.assetKey} wallpaper={assetOf(catalog, wearing('BACKGROUND'))} /></span>
        <span><b>{name}</b><small>{ROOM_SET_PARTS[slot]}</small>
          <small>{lockedItem ? (item.onSale ? `${item.pricePoints.toLocaleString('ko-KR')}포인트 · 눌러서 열기` : '지금은 열 수 없어요') : '가지고 있어요'}</small></span>
      </button>
    )
  }

  // ---- 방 소품 놓기(#705, core #723 계약안) ----
  const draftPlaced = draftDecor.map((d) => ({ ...d, assetKey: decorAsset(d.itemKey) }))
  const picked = pickedDecor !== null ? draftPlaced[pickedDecor] : undefined
  /** 놓을 수 있는 칸(고른 소품 기준). 길 검사가 들어 있어 고른 것·초안이 바뀔 때만 다시 센다 */
  const draftSig = decorKey(draftDecor)
  const pickedAsset = picked?.assetKey
  const placeCells = useMemo(() => (pickedAsset ? placeableCells(draftPlaced, pickedDecor, pickedAsset) : []),
    [draftSig, pickedDecor, pickedAsset]) // eslint-disable-line react-hooks/exhaustive-deps
  const placedCount = (itemKey: string) => draftDecor.filter((d) => d.itemKey === itemKey).length
  /** 저장돼 있지만 그릴 수 없는 소품(가구 배치·그림 목록이 바뀐 경우 등, #723): 방에 그리지 않고 "다시 놓아 주세요" */
  const drawnDraft = new Set(drawableDecor(draftPlaced))
  const staleOf = (itemKey: string) => draftPlaced.flatMap((p, i) => (p.itemKey === itemKey && !drawnDraft.has(p) ? [i] : []))
  /** [다시 놓기]: 그릴 수 없는 소품 하나를 가까운 놓을 수 있는 칸으로 옮기고 고른다 */
  const replaceStale = (i: number) => {
    setDecorMsg('')
    const p = draftPlaced[i]
    const spot = firstPlace(draftPlaced, p.assetKey, i)
    if (!spot) { setDecorMsg('지금은 놓을 자리가 없어요. 다른 소품을 치우거나 옮겨 보세요.'); return }
    setDraftDecor((d) => d.map((x, j) => (j === i ? { ...x, ...spot } : x)))
    setPickedDecor(i)
  }
  /** [놓기]: 가까운 놓을 수 있는 칸에 하나 놓고 그것을 고른다 */
  const placeNew = (item: LookItem) => {
    setDecorMsg('')
    if (draftDecor.length >= DECOR_SPOT_LIMIT) { setDecorMsg(`방 소품은 한 번에 ${DECOR_SPOT_LIMIT}개까지 놓을 수 있어요.`); return }
    if (placedCount(item.itemKey) >= (item.ownedCount ?? 0)) { setDecorMsg('가진 만큼 모두 놓았어요. 더 놓으려면 하나 더 사요.'); return }
    const spot = firstPlace(draftPlaced, item.assetKey ?? '')
    if (!spot) { setDecorMsg('지금은 놓을 자리가 없어요. 다른 소품을 치우거나 옮겨 보세요.'); return }
    setDraftDecor((d) => [...d, { ...spot, itemKey: item.itemKey, color: null }])
    setPickedDecor(draftDecor.length)
  }
  /** 고른 소품을 그 칸으로(초록 칸 누르기·화살표). 못 놓으면 까닭을 알린다 */
  const moveTo = (surface: DecorSurface, col: number, row: number) => {
    if (pickedDecor === null || !picked) return
    const why = placeProblem(draftPlaced, pickedDecor, { surface, col, row, assetKey: picked.assetKey })
    if (why) { setDecorMsg(why); return }
    setDecorMsg('')
    setDraftDecor((d) => d.map((x, i) => (i === pickedDecor ? { ...x, surface, col, row } : x)))
  }
  const nudge = (dir: 'left' | 'right' | 'up' | 'down') => {
    if (!picked) return
    const { dc, dr } = stepCell(picked.surface, dir)
    moveTo(picked.surface, picked.col + dc, picked.row + dr)
  }
  /** 고른 소품 색 바꾸기(놓은 것마다, core #758 color) */
  const paint = (color: string) => {
    if (pickedDecor === null) return
    setDraftDecor((d) => d.map((x, i) => (i === pickedDecor ? { ...x, color } : x)))
  }
  const removePicked = () => {
    if (pickedDecor === null) return
    setDraftDecor((d) => d.filter((_, i) => i !== pickedDecor))
    setPickedDecor(null)
    setDecorMsg('')
  }
  const decoring = editing && tab === 'decor' && decorReady
  // 방 소품 작은 카드(#705, 사용자 의견 2026-11-17 "이게 좀 어색하다"로 다시 짬): 한 줄에 나란히(좁은 화면은 옆으로 밀기)
  const decorChoice = (item: LookItem) => {
    const owned = item.ownedCount ?? 0
    const placedN = placedCount(item.itemKey)
    const stale = staleOf(item.itemKey)
    const price = item.pricePoints.toLocaleString('ko-KR')
    return (
      <div key={item.itemKey} className="st-decor-card">
        <span className="st-decor-thumb"><DecorThumb assetKey={item.assetKey} /></span>
        <b>{item.name}</b>
        <small>{decorPlaceText(item.assetKey)} · 놓음 {placedN}/{owned}</small>
        {stale.length > 0 && <small className="st-decor-stale">{stale.length}개는 다시 놓아 주세요</small>}
        <span className="st-decor-buttons">
          {stale.length > 0 ? (
            <button type="button" className="st-room-btn" disabled={!decorReady || saving} onClick={() => replaceStale(stale[0])}
              aria-label={`${item.name} 다시 놓기`}>다시 놓기</button>
          ) : (
            <button type="button" className="st-room-btn" disabled={!decorReady || placedN >= owned || saving} onClick={() => placeNew(item)}
              aria-label={`${item.name} 놓기`}>놓기</button>
          )}
          <button type="button" className="st-room-btn" disabled={!canBuyMore(item) || saving || shop.busy} onClick={() => shop.startPurchase(item.itemKey)}
            aria-label={owned >= DECOR_MAX_OWNED ? `${item.name} 더 살 수 없어요` : `${item.name} 1개 사기, ${price}포인트`}>
            {owned >= DECOR_MAX_OWNED ? '다 있어요' : !item.onSale ? '판매 끝' : `+사기 ${price}P`}
          </button>
        </span>
      </div>
    )
  }
  const pickedName = picked ? catalog?.find((i) => i.itemKey === picked.itemKey)?.name ?? '방 소품' : ''
  // 옮기기 판이 열리면 키보드 초점을 화살표로(목록 카드가 사라져 초점이 없어지지 않게)
  const padRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (pickedDecor !== null) padRef.current?.querySelector<HTMLButtonElement>('button')?.focus({ preventScroll: true })
  }, [pickedDecor === null]) // eslint-disable-line react-hooks/exhaustive-deps
  /** 옮기기 판에서 방향키로 한 칸씩 */
  const onMoveKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const dir = ({ ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' } as const)[e.key as 'ArrowUp']
    if (!dir) return
    e.preventDefault()
    nudge(dir)
  }
  // 옮기기를 시작하면 방이 보이게(좁은 화면은 서랍 아래에서 방이 화면 위로 밀려 있었음)
  useEffect(() => {
    if (pickedDecor === null || fit.w >= 700) return
    roomRef.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [pickedDecor === null]) // eslint-disable-line react-hooks/exhaustive-deps
  const bought = shop.purchase.data && catalog?.find((i) => i.itemKey === shop.purchase.data!.itemKey)

  return (
    <main className="st-paper st-sheet st-fit st-room-page">
      <div className="st-room-head">
        <h1 className="st-title-mix"><span>{child.nickname}의 </span>미니룸</h1>
        <div className="st-room-actions">
          {editing ? (
            <>
              <button type="button" className="st-room-btn" disabled={saving} onClick={cancel}>취소</button>
              <button type="button" className="st-room-btn st-room-go" disabled={saving || (!framesChanged && !lookChanged && !decorChanged) || lockedDraft || !!shop.confirming} onClick={() => void save()}>
                {saving ? '저장하는 중이에요' : '저장'}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="st-room-btn" onClick={() => onCustomize('friend')}>캐릭터·옷 꾸미기</button>
              <button type="button" className="st-room-btn st-room-go" disabled={!framesReady} onClick={() => startEdit()} data-tour="room-decor">{slots.isPending ? '방을 불러오고 있어요' : '방 꾸미기'}</button>
            </>
          )}
        </div>
      </div>
      <ErrorNotice error={look.error} retry={() => void look.refetch()} />
      {/* 걸린 액자 목록을 못 받으면 방 꾸미기를 열지 않는다(빈 목록으로 저장해 액자가 내려가지 않게) */}
      <ErrorNotice error={slots.error} retry={() => void slots.refetch()} />

      <section ref={roomRef} className="st-mini-room" aria-label="내 방">
        <div ref={holderRef} className="st-room-holder" style={{ height: Math.round(holderH), '--st-frame-wood': frameWood } as CSSProperties}>
          <div ref={stageRef} className={CAN_ROTATE || CAN_WALK ? 'st-room-stage' : 'st-room-stage is-fixed'} style={{ transform: stageTransform }} tabIndex={CAN_WALK ? 0 : undefined} role="group"
            aria-label={CAN_WALK ? '내 방 그림. 바닥을 누르면 걸어가고, 방을 누른 뒤 방향키로 움직여요. 가구 앞 발판에 서면 뭉치가 말을 걸어요' : '내 방 그림'}
            onKeyDown={onKeyDown} onKeyUp={onKeyUp} onBlur={onBlur} onPointerDown={onPointerDown}>
            <div className={`st-room-world${dragging ? ' is-dragging' : ''}`} data-top={WORLD_TOP}
              style={{ transform: `scale(${worldScale}) rotateX(${view.rx}deg) rotateY(${view.ry}deg)` }}>
              {faces.map((f) => {
                // 방 꾸미기에서 칸을 고르면 그 칸이 바꾸는 가구만 잠깐 반짝인다(사용자 의견 2026-11-16 "뭐가 어떻게 변하는지 보여야지")
                const g = glowClass(f.part, glow)
                return <div key={f.key + g.suffix} className={`st-f${f.floor && CAN_WALK ? ' st-room-floor' : ''}${g.cls}`} style={faceStyle(f)} onClick={f.floor && CAN_WALK ? onFloorClick : undefined} aria-hidden="true"
                  data-decor={f.key.startsWith('decor-') || undefined} />
              })}
              {/* 방 소품 놓기(#705): 놓인 소품을 눌러 고르고, 고른 소품은 주황 테두리, 놓을 수 있는 칸은 초록(누르면 옮김). 키보드는 서랍의 화살표 */}
              {decoring && draftPlaced.map((p, i) => {
                if (!drawnDraft.has(p)) return null
                const [w, h] = (cellsOf(p).reduce((a, c) => [Math.max(a[0], c.col - p.col + 1), Math.max(a[1], c.row - p.row + 1)], [1, 1]))
                const pl = cellPlane(p.surface, p.col, p.row, w, h)
                return <button key={`hit${i}`} type="button" tabIndex={-1} aria-hidden="true" className={`st-f st-decor-hit${i === pickedDecor ? ' is-picked' : ''}`}
                  style={{ width: pl.w, height: pl.h, marginLeft: -pl.w / 2, marginTop: -pl.h / 2, transform: pl.tf }}
                  onClick={() => { setPickedDecor(i); setDecorMsg('') }} />
              })}
              {decoring && picked && placeCells.map((c) => {
                const pl = cellPlane(c.surface, c.col, c.row)
                return <button key={`cell${c.surface}${c.col}-${c.row}`} type="button" tabIndex={-1} aria-hidden="true" className="st-f st-decor-cell"
                  style={{ width: pl.w, height: pl.h, marginLeft: -pl.w / 2, marginTop: -pl.h / 2, transform: pl.tf }}
                  onClick={() => moveTo(c.surface, c.col, c.row)} />
              })}
              {/* 꾸미는 중에는 가구 이름표를 숨기고 게시판 면에 붙은 글자만(누르지 않음). 평소 추억의 벽 이름표는 아래 가구 이름표와 같다(#1093) */}
              {editing && <div className="st-f st-room-boardtag" style={{ transform: boardTagTransform }} aria-hidden="true">추억의 벽</div>}
              {Array.from({ length: FRAME_SLOT_COUNT }, (_, i) => {
                const slotNo = i + 1
                const frame = frames.find((d) => d.slotNo === slotNo)
                const label = `${slotNo}번 자리${frame ? `: ${frame.title || '이름 없는 테마'}` : ' 비어 있음'}`
                const style = { transform: slotTransform(i, !!frame) }
                const g = frame ? glowClass('WALL', glow) : { cls: '', suffix: '' }
                const cls = `st-f st-room-slot${frame ? ' is-filled' : ''}${framing ? ' is-framing' : ''}${g.cls}`
                return framing ? (
                  <button key={slotNo} ref={(el) => { slotRefs.current[slotNo] = el }} type="button" className={cls} style={style}
                    aria-label={label} aria-pressed={picking === slotNo} disabled={saving}
                    onClick={() => setPicking(picking === slotNo ? null : slotNo)}>
                    {frame ? <FrameArt frame={frame} /> : <span>+ 걸기</span>}
                  </button>
                ) : (
                  <div key={slotNo + g.suffix} className={cls} style={style} role="img" aria-label={label}>
                    {frame && <FrameArt frame={frame} />}
                  </div>
                )
              })}
              {/* 가구 이름표: 걷지 않아도 누르면 바로 간다(늘 화면 쪽을 봄) */}
              {!editing && SPOTS.filter((s) => s.go).map((s) => (
                <button key={s.id} type="button" className={`st-f st-room-tag st-tag-${s.id}`} style={{ transform: `${faceCamera(s.tag.x, s.tag.y, s.tag.z)} scale(${s.tag.s})` }} onClick={s.go}>
                  {s.label}
                </button>
              ))}
              <div className={`st-f st-room-shadow${moving ? ' is-moving' : ''}`} aria-hidden="true"
                style={{ transform: `translate3d(${pos.x}px,-2px,${pos.z}px) rotateX(90deg) scale(${jumping ? 0.6 : 1})`, opacity: jumping ? 0.5 : 1 }} />
              <div className={`st-f st-room-char${moving || dragging ? ' is-moving' : ''}`} aria-hidden="true"
                style={{ transform: faceCamera(pos.x, jumping ? -70 : 0, pos.z) }}>
                <div className={moving ? 'st-room-walk' : 'st-room-bob'}>
                  <div style={{ transform: `scaleX(${facing})` }}><Companion kind={companion} size={140} decorative worn={worn} view={pose} /></div>
                </div>
              </div>
            </div>
          </div>
          {/* 발판에 서면 뭉치 말풍선 + 단추 하나(①). 방 그림 크기와 상관없이 읽히게 방 칸 위에 그린다 */}
          {bubble && (
            <SpeechBubble className="st-room-bubble" style={{ left: clamp(bubbleAt.x, 110, fit.w - 110), top: Math.max(bubbleAt.y, fit.w < 640 ? 96 : 120) }} role="group" aria-label="뭉치 말풍선">
              <p>{bubble.say}</p>
              {bubble.go && <button type="button" className="st-room-bubble-go" onClick={bubble.go}>{bubble.button}</button>}
              {bubble.more && <button type="button" className="st-room-bubble-go is-second" onClick={bubble.more.go}>{bubble.more.label}</button>}
            </SpeechBubble>
          )}
          {!editing && <button type="button" className="st-room-album" data-room-ui onClick={onAlbum}>
            <span className="st-room-thumb" aria-hidden="true">{thumb ? <FrameArt frame={thumb} /> : <span className="st-room-scene" />}</span>
            추억 앨범 열기
          </button>}
          {!editing && <RoomPanArrows points={shownDecor.map(decorCenter)} toHolder={toHolder} width={fit.w} limX={limX} panX={pan.x} panTo={panTo} />}
          {CAN_WALK && !editing && <p className="st-room-hint" data-room-ui aria-hidden="true">바닥을 누르면 걸어가요 · 방향키로 움직여요</p>}
          {CAN_ROTATE && (
            <div className="st-room-controls" data-room-ui>
              <span>끌어서 돌려 보기</span>
              <button type="button" aria-label="왼쪽으로 돌리기" onClick={() => turn(-12)}><RotateCcw aria-hidden="true" /></button>
              <button type="button" aria-label="오른쪽으로 돌리기" onClick={() => turn(12)}><RotateCw aria-hidden="true" /></button>
            </div>
          )}
        </div>

        {showNew && (
          <div className="st-room-new" role="status" data-room-ui>
            <button type="button" className="st-room-close" aria-label="새 액자 알림 닫기" onClick={dismissNew}><X aria-hidden="true" /></button>
            <strong>새 액자를 받았어요!</strong>
            <span>「{unseen[0].title || '이름 없는 테마'}」 다섯 문제를 모두 마쳤어요.{unseen.length > 1 && ` 새 액자가 ${unseen.length}개 있어요.`}</span>
            <button type="button" className="st-room-go" disabled={!framesReady} onClick={() => { dismissNew(); startEdit(firstEmpty) }}>벽에 걸어 보기</button>
          </div>
        )}

        {framing && picking !== null && (
          <div ref={pickerRef} className="st-room-picker" role="dialog" aria-label={`${picking}번 자리에 걸 액자`}
            onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); closePicker() } }}>
            <div className="st-room-picker-head">
              <h2>{picking}번 자리에 걸 액자</h2>
              <button type="button" className="st-room-close" aria-label="액자 고르기 닫기" onClick={closePicker}><X aria-hidden="true" /></button>
            </div>
            {slots.isPending || album.isPending ? <p role="status">추억의 벽을 불러오고 있어요.</p>
              : slots.error || album.error ? <ErrorNotice error={slots.error ?? album.error} retry={() => { void slots.refetch(); void album.refetch() }} />
              : !owned.length ? <p>아직 걸 액자가 없어요. 한 주 테마 문제 다섯 개를 모두 마무리하면 기념 액자를 받아요.</p>
              : (
                <ul>
                  {owned.map((f) => {
                    const current = !!pickingFrame && episodeKey(pickingFrame) === episodeKey(f)
                    const elsewhere = !current && draftFrames.some((d) => episodeKey(d) === episodeKey(f))
                    return (
                      <li key={episodeKey(f)}>
                        <button type="button" className="st-room-owned" aria-pressed={current} onClick={() => put(picking, f)}>
                          <span className="st-room-thumb" aria-hidden="true"><FrameArt frame={f} /></span>
                          <span><b>{f.title || '이름 없는 테마'}</b>
                            <small>{elsewhere ? '다른 자리에서 옮겨요' : `${weekLabel(f.weekStart)}${f.seen ? '' : ' · 새 액자'}`}</small></span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            {pickingFrame && <button type="button" className="st-room-btn st-room-clear" onClick={() => put(picking, null)}>이 자리 비우기</button>}
          </div>
        )}
        {/* 내 기록(PC 한 화면에서는 방 안 오른쪽 아래 작은 칩, 좁은 화면은 아래 카드 3장) */}
        {!editing && (
          <div className="st-room-chips" aria-label="내 기록" data-room-ui>
            <span className="st-room-chip is-purple">이번 주 <b>{theme ? solved : 0}</b> / 5 문제</span>
            <button type="button" className="st-room-chip is-yellow" onClick={onAlbum}>기념 액자 <b>{album.data?.totalElements ?? 0}</b>개 →</button>
          </div>
        )}
        <p className="st-room-note" role="status">{note}</p>
      </section>

      {/* 좁은 화면: 방 그림 속 이름표가 작아 같은 곳으로 가는 버튼을 아래에 둔다 */}
      {!editing && (
        <div className="st-room-quick">
          {SPOTS.filter((s) => s.go).map((s) => <button key={s.id} type="button" className="st-room-btn" onClick={s.go}>{s.label}</button>)}
        </div>
      )}

      {editing && (
        <section ref={drawerRef} className="st-room-drawer" aria-label="방 꾸미기">
          <div className="st-room-drawer-head">
            {tabs.map((x) => (
              <button key={x.id} type="button" aria-pressed={tab === x.id} onClick={() => { setTab(x.id); setPicking(null); shop.cancelUnlock(); setPickedDecor(null); setDecorMsg('') }}>{x.label}</button>
            ))}
            <span>{ROOM_TABS.find((x) => x.id === tab)!.hint}</span>
            {tab !== 'frames' && <b className="st-points-pill st-room-points" role="status">{shop.balance !== undefined ? `내 포인트 ${shop.balance.toLocaleString('ko-KR')}` : '포인트 확인 중'}</b>}
          </div>
          {tab === 'frames' && (
            <p className="st-room-drawer-note">
              {owned.length || album.isPending ? '방 그림에서 액자 자리를 누르면 걸 액자를 고를 수 있어요.'
                : '아직 걸 액자가 없어요. 한 주 테마 문제 다섯 개를 모두 마무리하면 기념 액자를 받아요.'}
            </p>
          )}
          {tab === 'wallpaper' && (
            <div className="st-room-choices">{[null, ...slotItems('BACKGROUND')].map((item) => choice('BACKGROUND', item))}</div>
          )}
          {tab === 'decor' && (
            <>
              {decorSpots.isPending && <p role="status" className="st-room-drawer-note">놓은 방 소품을 불러오고 있어요.</p>}
              <ErrorNotice error={decorSpots.error} retry={() => void decorSpots.refetch()} />
              {/* 고르는 모드: 소품 카드 한 줄 / 옮기는 모드: 목록은 숨기고 옮기기 판만(서랍이 짧아 방과 같이 보임) */}
              {!picked ? (
                <div className="st-decor-cards">{slotItems('DECOR').map(decorChoice)}</div>
              ) : (
                <div className="st-decor-move" role="group" aria-label={`${pickedName} 옮기기`} onKeyDown={onMoveKey}>
                  <div className="st-decor-move-head">
                    <span className="st-decor-thumb"><DecorThumb assetKey={picked.assetKey} color={picked.color} /></span>
                    <span><b>{pickedName} 옮기는 중</b><small>방의 초록 칸을 누르거나 화살표·방향키로 옮겨요.</small></span>
                  </div>
                  {decorColors(picked.assetKey).length > 1 && (
                    <div className="st-decor-colors" role="group" aria-label={`${pickedName} 색`}>
                      {decorColors(picked.assetKey).map((col) => (
                        <button key={col.key} type="button" aria-pressed={(decorColor(picked.assetKey, picked.color)?.key ?? '') === col.key} aria-label={col.label}
                          title={col.label} style={{ background: col.swatch }} onClick={() => paint(col.key)} />
                      ))}
                    </div>
                  )}
                  <div ref={padRef} className="st-decor-pad">
                    <button type="button" className="st-room-btn is-up" aria-label={picked.surface === 'FLOOR' ? '뒤로 한 칸' : '위로 한 칸'} onClick={() => nudge('up')}>↑</button>
                    <button type="button" className="st-room-btn is-left" aria-label="왼쪽으로 한 칸" onClick={() => nudge('left')}>←</button>
                    <button type="button" className="st-room-btn is-right" aria-label="오른쪽으로 한 칸" onClick={() => nudge('right')}>→</button>
                    <button type="button" className="st-room-btn is-down" aria-label={picked.surface === 'FLOOR' ? '앞으로 한 칸' : '아래로 한 칸'} onClick={() => nudge('down')}>↓</button>
                  </div>
                  <div className="st-decor-move-actions">
                    <button type="button" className="st-room-btn" onClick={removePicked}>치우기</button>
                    <button type="button" className="st-room-btn st-room-go" onClick={() => { setPickedDecor(null); setDecorMsg('') }}>다 놓았어요</button>
                  </div>
                </div>
              )}
              {decorMsg && <p role="alert" className="st-room-error">{decorMsg}</p>}
            </>
          )}
          {tab === 'floor' && (
            <div className="st-room-choices">{[null, ...slotItems('FLOOR')].map((item) => choice('FLOOR', item))}</div>
          )}
          {tab === 'furniture' && (
            <>
              {/* 가구를 하나씩 골라 보기(사용자 결정 2026-11-16): 13칸을 한꺼번에 두면 서랍 안 스크롤이 생겨, 한 번에 한 가구(4칸 안팎)만 한 줄로 */}
              <div className="st-room-furn-pick" role="group" aria-label="바꿀 가구">
                {FURNITURE_SLOTS.map((slot) => (
                  <button key={slot} type="button" aria-pressed={furn === slot} onClick={() => setFurn(slot)}>
                    {SLOT_LABELS[slot]}
                    {(draftLook[slot] ?? equipped[slot] ?? null) !== (equipped[slot] ?? null) && <i aria-label="바꾼 가구" />}
                  </button>
                ))}
              </div>
              <div className="st-room-choices" role="group" aria-label={SLOT_LABELS[furn]}>
                {[null, ...slotItems(furn)].map((item) => choice(furn, item))}
              </div>
            </>
          )}
          {tab !== 'frames' && <UnlockConfirm shop={shop} />}
          {tab !== 'frames' && (shop.unlock.isPending || shop.unlock.isSuccess) && (
            <p role="status" className="st-room-drawer-note">{shop.unlock.isPending ? '여는 중이에요.' : '열었어요! 저장을 누르면 내 방에 반영돼요.'}</p>
          )}
          {tab === 'decor' && (shop.purchase.isPending || shop.purchase.isSuccess) && (
            <p role="status" className="st-room-drawer-note">{shop.purchase.isPending ? '사는 중이에요.' : `샀어요! ${josa.subject(bought ? bought.name : '방 소품')} ${shop.purchase.data!.ownedCount}개 있어요.`}</p>
          )}
          {tab === 'decor' && shop.purchase.isError && (unlockMessage(shop.purchase.error)
            ? <p role="alert" className="st-room-error">{unlockMessage(shop.purchase.error)}</p> : <ErrorNotice error={shop.purchase.error} />)}
          {tab !== 'frames' && shop.unlock.isError && (unlockMessage(shop.unlock.error)
            ? <p role="alert" className="st-room-error">{unlockMessage(shop.unlock.error)}</p> : <ErrorNotice error={shop.unlock.error} />)}
          {lockedDraft && !shop.confirming && <p role="status" className="st-room-error">아직 안 연 것을 골랐어요. 열거나 다른 것을 골라야 저장할 수 있어요.</p>}
          {errors.map((m) => <p key={m} role="alert" className="st-room-error">{m}</p>)}
        </section>
      )}

      <section className="st-room-records" aria-label="내 기록">
        <div className="st-room-record is-purple">
          <span>이번 주 푼 문제</span>
          <strong>{theme ? solved : 0}<small> / 5</small></strong>
          <p>{theme || weekly.isPending ? '다섯 문제를 모두 마치면 기념 액자를 받아요' : weekly.isError ? '이번 주 테마를 불러오지 못했어요' : '이번 주 테마가 열리면 여기에 쌓여요'}</p>
        </div>
        <div className="st-room-record is-yellow">
          <span>기념 액자</span>
          <strong>{album.data?.totalElements ?? 0}<small> 개</small></strong>
          <button type="button" className="st-room-link" onClick={onAlbum}>추억 앨범에서 보기 →</button>
        </div>
      </section>
    </main>
  )
}
