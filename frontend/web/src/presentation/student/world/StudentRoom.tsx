import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from 'react'
import { RotateCcw, RotateCw, X } from 'lucide-react'
import { useSaveLook, useStudentLook } from '../../../data/studentLook/queries.ts'
import { useAlbum, useFrameSlots, useLookItems, useMarkFramesSeen, useSaveFrameSlots, useWeeklyTheme } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { episodeKey, FRAME_SLOT_COUNT, FURNITURE_SLOTS, NO_EQUIPPED, SLOT_LABELS, weekLabel } from '../../../domain/retention.ts'
import type { AlbumItem, FrameSlot, FurnitureSlot, LookItem } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import type { FriendView } from './friendArt.ts'
import { SpeechBubble } from './SpeechBubble.tsx'
import { boardTagTransform, WORLD_TOP, DESK_X, DESK_Z, DOOR, faceStyle, MAT_RADIUS, MATS, onFloor, projectToHolder, ROOM, roomFaces, RUG, SHELF, slotTransform, WARDROBE, WINDOW_Z } from './roomArt.ts'
import type { MatId } from './roomArt.ts'
import { furnitureSkinName, ROOM_SET_PARTS, skinOf, wallpaperOf } from './roomAssets.ts'
import type { RoomSlot } from './roomAssets.ts'
import { FurnitureThumb } from './FurnitureThumb.tsx'
import { FrameScene } from './FrameScene.tsx'
import { glowClass, useGlow } from './roomGlow.ts'
import type { CustomizeTab } from './lookShop.ts'
import { useLook } from './lookContext.ts'
import './room.css'

type Placed = { slotNo: number; themeId: string; weekStart: string; title: string; imageUrl: string | null }
/** 내 방에서 바꾸는 착용 칸: 벽지(배경 아이템)와 가구 3종 */
type RoomTab = 'frames' | 'wallpaper' | 'furniture'
const ROOM_TABS: { id: RoomTab; label: string; hint: string }[] = [
  { id: 'frames', label: '액자 걸기', hint: '빈 자리를 눌러 기념 액자를 걸어요.' },
  { id: 'wallpaper', label: '벽지', hint: '벽지·바닥·러그·커튼이 같이 바뀌어요. 새 벽지는 꾸미기 ‘내 방 가구’에서 열어요.' },
  { id: 'furniture', label: '가구', hint: '책상·책장, 추억의 벽·액자, 옷장·문이 같이 바뀌어요.' },
]
/**
 * 캐릭터 걷기(바닥 누르기·방향키·스페이스 점프). 사용자 결정 2026-11-16으로 켬(기능명세 P27 문구도 고침).
 * 화면 안에서만 움직이고 자리는 저장하지 않는다. 보이는 바닥 안·가구 밖·방 위 단추 자리 밖에서만 선다.
 */
const CAN_WALK = true
/** 걷는 빠르기(방 좌표/초): 갈 곳 사이가 1~2초쯤(230에서 올림, 사용자 의견 2026-11-16 "움직이는 속도 좀 빠르게") */
const SPEED = 380
/** 방 돌려 보기: 방 안 시점(벽·바닥이 창 밖까지)이라 돌리면 방 끝이 드러나 끔(사용자 의견 2026-11-15 "디오라마 말고") */
const CAN_ROTATE = false
const START: { rx: number; ry: number; x: number; z: number } = { rx: -24, ry: -30, x: RUG.x, z: RUG.z }
const MOVE_KEYS: Record<string, 'u' | 'd' | 'l' | 'r'> = {
  ArrowUp: 'u', KeyW: 'u', ArrowDown: 'd', KeyS: 'd', ArrowLeft: 'l', KeyA: 'l', ArrowRight: 'r', KeyD: 'r',
}
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

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

/** 액자 속 그림이 없을 때 쓰는 작은 풍경. 회차마다 언덕 색만 달라진다 */
function FrameArt({ frame }: { frame: { themeId: string; title?: string; imageUrl: string | null } }) {
  if (frame.imageUrl) return <img src={frame.imageUrl} alt="" />
  // 회차마다 다른 장면(앨범과 같은 FrameScene, 사용자 의견 2026-11-16 "액자도 그림이 너무 일정해")
  return <FrameScene className="st-room-scene" themeId={frame.themeId} title={frame.title} />
}

/**
 * 내 방(/student/room, P27·FN-RET-09, #556·#648). 시안 MyPage의 그림체를 방 안 시점·고정 시점으로 그린다.
 * 사용자 결정 2026-11-16: 가구 = 메뉴. 러그에서 출발한 뭉치가 바닥을 누르거나 방향키로 걸어가 갈 곳 앞 발판에 서면 말풍선 단추로 간다
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
  // 저장·취소 알림은 잠시 보이고 사라진다(화면 읽기 프로그램은 바뀔 때 읽음)
  useEffect(() => {
    if (!note) return
    const id = window.setTimeout(() => setNote(''), 4000)
    return () => clearTimeout(id)
  }, [note])
  const frames = editing ? draftFrames : placed
  const { glow, flash } = useGlow()
  const wearing = (slot: RoomSlot) => (editing && slot in draftLook ? draftLook[slot] ?? null : equipped[slot] ?? null)
  const framesChanged = editing && !sameFrames(draftFrames, placed)
  const lookChanged = editing && (Object.keys(draftLook) as RoomSlot[]).some((s) => (draftLook[s] ?? null) !== (equipped[s] ?? null))
  const slotItems = (slot: RoomSlot) => (catalog ?? []).filter((i) => i.slot === slot)
  const tabs = ROOM_TABS.filter((x) => x.id === 'frames' || (x.id === 'wallpaper' ? slotItems('BACKGROUND').length > 0 : FURNITURE_SLOTS.some((s) => slotItems(s).length > 0)))

  const startEdit = (slotNo: number | null = null) => {
    setDraftFrames(placed)
    setDraftLook({})
    setTab('frames')
    setPicking(slotNo)
    setErrors([])
    setNote('')
    setEditing(true)
  }
  const cancel = () => {
    setEditing(false)
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
    const kinds: ('frames' | 'look')[] = []
    if (framesChanged) {
      kinds.push('frames')
      jobs.push(saveFrames.mutateAsync(draftFrames.map(({ slotNo, themeId, weekStart }) => ({ slotNo, themeId, weekStart }))))
    }
    if (lookChanged) {
      kinds.push('look')
      jobs.push(saveLook.mutateAsync({ theme: t.id, companion, equipped: { ...equipped, ...draftLook } }))
    }
    const results = await Promise.allSettled(jobs)
    setSaving(false)
    const failed = results.flatMap((r, i) => (r.status === 'rejected' ? [kinds[i] === 'frames' ? frameSaveMessage(r.reason) : LOOK_SAVE_FAILED] : []))
    if (failed.length) {
      setErrors(failed)
      return
    }
    setEditing(false)
    setPicking(null)
    setNote(kinds.length === 1 && kinds[0] === 'frames' ? '추억의 벽을 저장했어요.' : '내 방을 저장했어요.')
  }

  // ---- 방 보기(돌리기·움직이기) 상태 ----
  const [view, setView] = useState({ rx: START.rx, ry: START.ry })
  const [dragging, setDragging] = useState(false)
  const [pos, setPos] = useState({ x: START.x, z: START.z })
  const [facing, setFacing] = useState(1)
  // 걷는 방향 모습(캔버스 MyPage: 안쪽으로 가면 뒷모습, 앞으로 오면 앞모습, 옆으로 가면 옆모습, 멈추면 잠시 뒤 앞모습)
  const [pose, setPose] = useState<FriendView>('front')
  const idleView = useRef<number | undefined>(undefined)
  const lookBy = (scrX: number, scrUp: number) => {
    window.clearTimeout(idleView.current)
    setPose(Math.abs(scrUp) > Math.abs(scrX) ? (scrUp > 0 ? 'back' : 'front') : 'side')
  }
  const [moving, setMoving] = useState(false)
  const [jumping, setJumping] = useState(false)
  const stageRef = useRef<HTMLDivElement>(null)
  const holderRef = useRef<HTMLDivElement>(null)
  const keys = useRef<Record<string, boolean>>({})
  const raf = useRef<number | null>(null)
  const lastT = useRef(0)
  const path = useRef<{ x: number; z: number }[]>([])
  const drag = useRef<{ x: number; y: number; rx: number; ry: number; moved: boolean } | null>(null)
  const justDragged = useRef(false)
  const timers = useRef<number[]>([])
  const viewRef = useRef(view)
  const posRef = useRef(pos)
  /** 화면 좌표 계산에 쓰는 지금 크기(그릴 때마다 갱신) */
  const metrics = useRef({ ws: 0.92, stageScale: 0.8, holderW: 1200, holderH: 600 })
  useLayoutEffect(() => { viewRef.current = view; posRef.current = pos }, [view, pos])
  const later = (fn: () => void, ms: number) => { timers.current.push(window.setTimeout(fn, ms)) }
  useEffect(() => () => {
    if (raf.current) cancelAnimationFrame(raf.current)
    timers.current.forEach((id) => clearTimeout(id))
  }, [])
  const reducedMotion = () => typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  /**
   * 설 수 있는 곳: 바닥 안·가구 밖(onFloor)이고, 화면에 뭉치가 다 보이며(방 칸 밖으로 나가지 않음)
   * 방 위 단추(왼쪽 아래 추억 앨범·새 액자 알림, 오른쪽 아래 내 기록 칩, 오른쪽 위 안내, `data-room-ui`)와 겹치지 않는 곳
   */
  const standable = (x: number, z: number, ignoreUi = false) => {
    if (!onFloor(x, z)) return false
    const m = metrics.current
    const foot = projectToHolder(x, 0, z, { ...viewRef.current, ws: m.ws, stageScale: m.stageScale, holderW: m.holderW })
    const k = m.ws * m.stageScale
    const half = 54 * k
    const tall = 140 * k
    const box = { l: foot.x - half, r: foot.x + half, t: foot.y - tall, b: foot.y + 6 * k }
    if (box.l < 6 || box.r > m.holderW - 6 || box.t < 6 || box.b > m.holderH - 4) return false
    if (ignoreUi) return true
    const holder = holderRef.current?.getBoundingClientRect()
    if (!holder) return true
    const ui = holderRef.current?.parentElement?.querySelectorAll<HTMLElement>('[data-room-ui]') ?? []
    for (const el of ui) {
      const r = el.getBoundingClientRect()
      if (!r.width) continue
      const pad = 10
      if (box.r > r.left - holder.left - pad && box.l < r.right - holder.left + pad &&
          box.b > r.top - holder.top - pad && box.t < r.bottom - holder.top + pad) return false
    }
    return true
  }
  /**
   * 한 걸음 갈 수 있나. 지금 자리가 이미 방 위 단추와 겹쳐 있으면(좁은 화면에서 추억 앨범 단추가 러그 출발 자리를 덮음)
   * 단추 규칙만 빼고 보아 빠져나갈 수 있게 한다 — 예전에는 첫걸음부터 막혀 모바일에서 뭉치가 꼼짝 못 했음(사용자 의견 2026-11-16 "이 화면일 때 안 움직이네")
   */
  const canStep = (from: { x: number; z: number }, to: { x: number; z: number }) =>
    standable(to.x, to.z) || (!standable(from.x, from.z) && standable(to.x, to.z, true))
  /** from에서 to로 곧게 갈 때 설 수 있는 마지막 자리 */
  const reach = (from: { x: number; z: number }, to: { x: number; z: number }) => {
    const n = Math.max(1, Math.ceil(Math.hypot(to.x - from.x, to.z - from.z) / 12))
    let last = from
    for (let i = 1; i <= n; i++) {
      const p = { x: from.x + ((to.x - from.x) * i) / n, z: from.z + ((to.z - from.z) * i) / n }
      if (!canStep(last, p)) break
      last = p
    }
    return last
  }
  const gap = (a: { x: number; z: number }, b: { x: number; z: number }) => Math.hypot(a.x - b.x, a.z - b.z)
  const faceTo = (dx: number, dz: number) => {
    const th = (viewRef.current.ry * Math.PI) / 180
    const sx = dx * Math.cos(th) + dz * Math.sin(th)
    if (Math.abs(sx) > 0.5) setFacing(sx < 0 ? -1 : 1)
    lookBy(sx, dx * Math.sin(th) - dz * Math.cos(th))
  }
  const tick = (t: number) => {
    const dt = lastT.current ? Math.min(0.05, (t - lastT.current) / 1000) : 1 / 60
    lastT.current = t
    let { x, z } = posRef.current
    const k = keys.current
    const sx = (k.r ? 1 : 0) - (k.l ? 1 : 0)
    const sy = (k.u ? 1 : 0) - (k.d ? 1 : 0)
    if (sx || sy) {
      // 방향키: 보는 각도 기준(위 = 방 안쪽, 오른쪽 = 화면 오른쪽)
      path.current = []
      const th = (viewRef.current.ry * Math.PI) / 180
      const sp = (SPEED * dt) / Math.hypot(sx, sy)
      const dx = (sx * Math.cos(th) + sy * Math.sin(th)) * sp
      const dz = (sx * Math.sin(th) - sy * Math.cos(th)) * sp
      if (canStep({ x, z }, { x: x + dx, z })) x += dx
      if (canStep({ x, z }, { x, z: z + dz })) z += dz
      if (sx) setFacing(sx < 0 ? -1 : 1)
      lookBy(sx, sy)
    } else if (path.current.length) {
      // 바닥을 누른 곳으로 걷기
      const next = path.current[0]
      const d = Math.hypot(next.x - x, next.z - z)
      const step = SPEED * dt
      faceTo(next.x - x, next.z - z)
      if (d <= step) { x = next.x; z = next.z; path.current.shift() }
      else { x += ((next.x - x) / d) * step; z += ((next.z - z) / d) * step }
    } else {
      raf.current = null
      lastT.current = 0
      setMoving(false)
      window.clearTimeout(idleView.current)
      idleView.current = window.setTimeout(() => { setPose('front'); setFacing(1) }, 1200)
      return
    }
    posRef.current = { x, z }
    setPos({ x, z })
    setMoving(true)
    raf.current = requestAnimationFrame(tick)
  }
  const run = () => { if (!raf.current) { lastT.current = 0; raf.current = requestAnimationFrame(tick) } }
  /** 바닥을 누른 곳으로 걸어간다. 곧게 못 가면 러그·발판 한 곳을 거쳐 가고, 그래도 막히면 갈 수 있는 데까지 */
  const walkTo = (target: { x: number; z: number }) => {
    const from = posRef.current
    const direct = reach(from, target)
    let route: { x: number; z: number }[] = [direct]
    if (gap(direct, target) > 14) {
      let best = { left: gap(direct, target), len: gap(from, direct) }
      for (const via of [RUG, ...MATS]) {
        if (gap(reach(from, via), via) > 6) continue
        const second = reach(via, target)
        const left = gap(second, target)
        const len = gap(from, via) + gap(via, second)
        if (left < best.left - 4 || (Math.abs(left - best.left) <= 4 && len < best.len)) { best = { left, len }; route = [{ x: via.x, z: via.z }, second] }
      }
    }
    const end = route[route.length - 1]
    if (gap(end, from) < 2) return
    if (reducedMotion()) {
      // 움직임 줄이기: 걷는 모습 없이 그 자리로 바로
      faceTo(end.x - from.x, end.z - from.z)
      path.current = []
      posRef.current = end
      setPos(end)
      return
    }
    path.current = route
    run()
  }
  /** 방향키·WASD로 움직이기, 스페이스 점프. 방 그림에 초점이 있을 때만(안의 버튼·페이지 스크롤은 그대로) */
  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!CAN_WALK || e.target !== e.currentTarget || editing) return
    if (e.code === 'Space') {
      e.preventDefault()
      if (!jumping && !reducedMotion()) { setJumping(true); later(() => setJumping(false), 380) }
      return
    }
    const k = MOVE_KEYS[e.code]
    if (!k) return
    e.preventDefault()
    keys.current[k] = true
    run()
  }
  const onKeyUp = (e: ReactKeyboardEvent<HTMLDivElement>) => { const k = MOVE_KEYS[e.code]; if (k) keys.current[k] = false }
  const onBlur = () => { keys.current = {} }
  /** 방을 누르면 초점(방향키용). 끌어서 돌려 보기는 CAN_ROTATE일 때만 */
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button, a')) return
    if (CAN_WALK) stageRef.current?.focus({ preventScroll: true })
    if (!CAN_ROTATE) return
    drag.current = { x: e.clientX, y: e.clientY, rx: viewRef.current.rx, ry: viewRef.current.ry, moved: false }
    const move = (ev: PointerEvent) => {
      const d = drag.current
      if (!d) return
      const dx = ev.clientX - d.x
      const dy = ev.clientY - d.y
      if (!d.moved && Math.abs(dx) + Math.abs(dy) < 5) return
      d.moved = true
      setDragging(true)
      setView({ ry: clamp(d.ry + dx * 0.18, -50, -12), rx: clamp(d.rx - dy * 0.1, -40, -10) })
    }
    const up = () => {
      justDragged.current = !!drag.current?.moved
      drag.current = null
      setDragging(false)
      later(() => { justDragged.current = false }, 0)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
  }
  /** 바닥 누르기: 바닥 면 안 좌표 → 방 좌표 */
  const onFloorClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (justDragged.current || editing) return
    const { offsetX, offsetY } = e.nativeEvent
    walkTo({ x: offsetX - ROOM.W / 2, z: offsetY - ROOM.D / 2 })
  }
  const turn = (d: number) => setView((v) => ({ ...v, ry: clamp(v.ry + d, -50, -12) }))
  const faceCamera = (x: number, y: number, z: number) => `translate3d(${x}px,${y}px,${z}px) rotateY(${-view.ry}deg) rotateX(${-view.rx}deg)`
  /** 뭉치가 올라선 발판(걷는 중이 아닐 때) */
  // 가장 가까운 가구 앞(반지름 안)이면 그 말풍선
  const near = MATS.map((m) => ({ id: m.id, d: Math.hypot(m.x - pos.x, m.z - pos.z) })).filter((m) => m.d < MAT_RADIUS).sort((a, b) => a.d - b.d)[0]
  const onMat: MatId | null = !moving && !editing ? near?.id ?? null : null

  // ---- 크기: 창 높이에 맞춰 방을 줄인다(시안: 제목 아래 남은 높이, 꾸미기 서랍이 열리면 그만큼 더) ----
  const roomRef = useRef<HTMLElement>(null)
  const drawerRef = useRef<HTMLElement>(null)
  const [fit, setFit] = useState({ w: 1200, h: Infinity })
  useLayoutEffect(() => {
    const el = roomRef.current
    if (!el) return
    const measure = () => {
      const stage = el.closest('.st-stage')
      let h = Infinity
      if (stage && window.matchMedia('(min-width: 901px) and (min-height: 520px)').matches) {
        const top = el.getBoundingClientRect().top - stage.getBoundingClientRect().top + stage.scrollTop
        h = stage.clientHeight - top - 24 - (drawerRef.current ? drawerRef.current.offsetHeight + 14 : 0)
      }
      setFit((before) => (before.w === el.clientWidth && before.h === h ? before : { w: el.clientWidth, h }))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    if (drawerRef.current) ro.observe(drawerRef.current)
    window.addEventListener('resize', measure)
    return () => { ro.disconnect(); window.removeEventListener('resize', measure) }
  }, [editing])
  // PC(901px 이상·창 높이 700px 이상)는 스크롤 없이 한 화면(사용자 의견 2026-11-15 "스크롤을 해야 하는 게 말이 안 돼"):
  // 방 칸은 칸 폭 전체 × 제목 아래 남은 높이. 방 안 시점이라 벽·바닥이 창 밖까지 이어져 높이에 맞춰 줄여도 양옆이 비지 않는다.
  // 좁은 화면은 문서 전체를 내려 보는 방식 그대로, 무대 폭을 1060으로 보고 크게(오른쪽 끝 문까지 보이는 한도, 2026-11-16)
  const oneScreen = Number.isFinite(fit.h)
  const holderH = oneScreen ? Math.max(editing ? 210 : 240, Math.min(fit.h, 780 * (fit.w / 1400))) : 780 * Math.min(1.2, fit.w / (fit.w < 700 ? 1060 : 1400))
  const scale = Math.max(0.2, Math.min(1.2, oneScreen ? Math.min(fit.w / 1400, holderH / 780) : fit.w / (fit.w < 700 ? 1060 : 1400)))
  // 방이 무대를 넉넉히 채우게(0.72에서 키움, 사용자 의견 2026-11-15 "너무 작아 보여")
  // 빈 벽 여백을 줄이게 더 당김(사용자 의견 2026-11-16 "여백이 너무 넓어")
  const worldScale = fit.w < 700 ? 0.92 : 1.0

  const faces = roomFaces({
    wallpaper: assetOf(catalog, wearing('BACKGROUND')),
    desk: assetOf(catalog, wearing('DESK')),
    wall: assetOf(catalog, wearing('WALL')),
    wardrobe: assetOf(catalog, wearing('WARDROBE')),
  }, onMat)
  const framing = editing && tab === 'frames'
  const showNew = !editing && !newSeen && unseen.length > 0
  const firstEmpty = Array.from({ length: FRAME_SLOT_COUNT }, (_, i) => i + 1).find((n) => !placed.some((p) => p.slotNo === n)) ?? null
  const pickingFrame = picking !== null ? frames.find((d) => d.slotNo === picking) : undefined
  const thumb = placed[0] ?? owned[0]
  const theme = weekly.data
  const solved = theme ? theme.days.filter((d) => d.attemptStatus === 'COMPLETED').length : 0

  // 걷기 경계 계산용 지금 크기
  useLayoutEffect(() => { metrics.current = { ws: worldScale, stageScale: scale, holderW: fit.w, holderH } }, [worldScale, scale, fit.w, holderH])
  /** 추억의 벽 액자 나무 틀 색(추억의 벽 스킨 세트) */
  const frameWood = skinOf('WALL', assetOf(catalog, wearing('WALL'))).set[0]

  /**
   * 갈 곳 6개(사용자 결정 2026-11-16 ① 가구 = 메뉴): 이름표(누르면 바로)와 발판 말풍선(뭉치가 서면 단추 하나).
   * 추억의 벽 이름표는 게시판 위 이름표가 맡는다.
   */
  // 이름표는 화면 쪽으로 돌아가 있어 오른쪽 위 모서리가 뒤로 들어간다(기본 시점 약 73px, 돌리기를 켜면 끝 시점 ry -50·rx -40에서 약 106px) → 뒷벽에서 110px 넘게 띄움
  // (옷장 이름표가 뒷벽에서 66px라 오른쪽이 벽에 잘리던 것, 사용자 의견 2026-11-16 "이것도 잘린다").
  // 창문 이름표는 -420이면 책장 이름표 왼쪽 위를 가려서(1440에서 30×8px 겹침) -446으로 올림
  const SPOTS: { id: MatId; label: string; tag: { x: number; y: number; z: number }; say: string; button: string; go?: () => void; more?: { label: string; go: () => void }; ownTag?: boolean }[] = [
    { id: 'desk', label: '책상 · 오늘 문제', tag: { x: DESK_X + 40, y: -175, z: DESK_Z + 20 }, say: '오늘 문제 풀래?', button: '오늘 문제 풀기', go: onTheme },
    { id: 'window', label: '창문 · 이번 주 이야기', tag: { x: -ROOM.W / 2 + 120, y: -446, z: WINDOW_Z - 20 }, say: '이번 주 이야기 다시 볼까?', button: '이야기 보기', go: onStory ?? onTheme },
    { id: 'board', label: '추억의 벽 · 액자', tag: { x: 0, y: 0, z: 0 }, say: '액자 볼까?', button: '추억 앨범 열기', go: onAlbum, ownTag: true },
    { id: 'wardrobe', label: '옷장 · 옷 갈아입기', tag: { x: WARDROBE.x, y: -405, z: WARDROBE.z + 60 }, say: '옷 갈아입을까?', button: '옷 갈아입기', go: () => onCustomize('wear'),
      more: { label: '뭉치 친구 바꾸기', go: onFriends } },
    { id: 'door', label: '문 · 친구 생각', tag: { x: DOOR.x - 20, y: -330, z: -ROOM.D / 2 + 120 }, say: '친구들 생각 보러 갈까?', button: '친구 생각 보기', go: onCommunity },
    { id: 'shelf', label: '책장 · 내 공책', tag: { x: SHELF.x, y: -285, z: SHELF.z + 60 }, say: '내 공책 볼까?', button: '내 공책 열기', go: onJournal },
  ]
  const bubble = onMat ? SPOTS.find((s) => s.id === onMat) : undefined
  const bubbleAt = projectToHolder(pos.x, -150, pos.z, { ...view, ws: worldScale, stageScale: scale, holderW: fit.w })

  // 액자 고르기 창: 열리면 첫 버튼으로, Esc로 닫으면 그 자리 버튼으로 초점을 돌린다
  const pickerRef = useRef<HTMLDivElement>(null)
  const slotRefs = useRef<Record<number, HTMLButtonElement | null>>({})
  useEffect(() => { if (picking !== null) pickerRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus() }, [picking])
  const closePicker = () => { const n = picking; setPicking(null); if (n !== null) slotRefs.current[n]?.focus() }

  const choice = (slot: RoomSlot, item: LookItem | null) => {
    const key = item?.itemKey ?? null
    const selected = wearing(slot) === key
    const lockedItem = !!item && !item.unlocked
    const name = item ? item.name : slot === 'BACKGROUND' ? `${wallpaperOf(null).name} (기본)` : `${furnitureSkinName(slot, null)} (기본)`
    return (
      <button key={`${slot}:${key ?? 'none'}`} type="button" className="st-room-choice" aria-pressed={selected} disabled={lockedItem || saving}
        onClick={() => { setDraftLook((d) => ({ ...d, [slot]: key })); setErrors([]); flash(slot) }}>
        {/* 색 네모 대신 그 칸이 바꾸는 가구 그림(세트 포함), 아래 줄에 함께 바뀌는 것 */}
        <span className="st-room-swatch"><FurnitureThumb slot={slot} assetKey={item?.assetKey} /></span>
        <span><b>{name}</b><small>{ROOM_SET_PARTS[slot]}</small>
          <small>{lockedItem ? (item.onSale ? `${item.pricePoints.toLocaleString('ko-KR')}포인트 · 꾸미기에서 열기` : '지금은 열 수 없어요') : '가지고 있어요'}</small></span>
      </button>
    )
  }

  return (
    <main className="st-paper st-sheet st-fit st-room-page">
      <div className="st-room-head">
        <h1 className="st-title-mix"><span>{child.nickname}의 </span>미니룸</h1>
        <div className="st-room-actions">
          {editing ? (
            <>
              <button type="button" className="st-room-btn" disabled={saving} onClick={cancel}>취소</button>
              <button type="button" className="st-room-btn st-room-go" disabled={saving || (!framesChanged && !lookChanged)} onClick={() => void save()}>
                {saving ? '저장하는 중이에요' : '저장'}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="st-room-btn" onClick={() => onCustomize('friend')}>캐릭터·옷 꾸미기</button>
              <button type="button" className="st-room-btn st-room-go" onClick={() => startEdit()}>방 꾸미기</button>
            </>
          )}
        </div>
      </div>
      <ErrorNotice error={look.error} retry={() => void look.refetch()} />

      <section ref={roomRef} className="st-mini-room" aria-label="내 방">
        <div ref={holderRef} className="st-room-holder" style={{ height: Math.round(holderH), '--st-frame-wood': frameWood } as CSSProperties}>
          <div ref={stageRef} className={CAN_ROTATE || CAN_WALK ? 'st-room-stage' : 'st-room-stage is-fixed'} style={{ transform: `scale(${scale.toFixed(3)})` }} tabIndex={CAN_WALK ? 0 : undefined} role="group"
            aria-label={CAN_WALK ? '내 방 그림. 바닥을 누르면 걸어가고, 방을 누른 뒤 방향키로 움직여요. 가구 앞 발판에 서면 뭉치가 말을 걸어요' : '내 방 그림'}
            onKeyDown={onKeyDown} onKeyUp={onKeyUp} onBlur={onBlur} onPointerDown={onPointerDown}>
            <div className={`st-room-world${dragging ? ' is-dragging' : ''}`} data-top={WORLD_TOP}
              style={{ transform: `scale(${worldScale}) rotateX(${view.rx}deg) rotateY(${view.ry}deg)` }}>
              {faces.map((f) => {
                // 방 꾸미기에서 칸을 고르면 그 칸이 바꾸는 가구만 잠깐 반짝인다(사용자 의견 2026-11-16 "뭐가 어떻게 변하는지 보여야지")
                const g = glowClass(f.part, glow)
                return <div key={f.key + g.suffix} className={`st-f${f.floor && CAN_WALK ? ' st-room-floor' : ''}${g.cls}`} style={faceStyle(f)} onClick={f.floor && CAN_WALK ? onFloorClick : undefined} aria-hidden="true" />
              })}
              {editing ? (
                <div className="st-f st-room-boardtag" style={{ transform: boardTagTransform }} aria-hidden="true">추억의 벽</div>
              ) : (
                <button type="button" className="st-f st-room-boardtag" style={{ transform: boardTagTransform }} onClick={onAlbum}>추억의 벽 · 액자</button>
              )}
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
              {!editing && SPOTS.filter((s) => s.go && !s.ownTag).map((s) => (
                <button key={s.id} type="button" className={`st-f st-room-tag st-tag-${s.id}`} style={{ transform: faceCamera(s.tag.x, s.tag.y, s.tag.z) }} onClick={s.go}>
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
          <button type="button" className="st-room-album" data-room-ui onClick={onAlbum}>
            <span className="st-room-thumb" aria-hidden="true">{thumb ? <FrameArt frame={thumb} /> : <span className="st-room-scene" />}</span>
            추억 앨범 열기
          </button>
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
            <button type="button" className="st-room-go" onClick={() => { dismissNew(); startEdit(firstEmpty) }}>벽에 걸어 보기</button>
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
            <button type="button" className="st-room-chip is-green" onClick={() => onCustomize()}>꾸미기 →</button>
            <button type="button" className="st-room-chip" onClick={onFriends}>뭉치 친구들 →</button>
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
              <button key={x.id} type="button" aria-pressed={tab === x.id} onClick={() => { setTab(x.id); setPicking(null) }}>{x.label}</button>
            ))}
            <span>{ROOM_TABS.find((x) => x.id === tab)!.hint}</span>
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
        <div className="st-room-record is-green">
          <span>나만의 꾸미기</span>
          <strong className="st-room-record-words">테마 · 캐릭터 · 옷 · 가구</strong>
          <span className="st-room-links">
            <button type="button" className="st-room-link" onClick={() => onCustomize()}>꾸미기 열기 →</button>
            <button type="button" className="st-room-link" onClick={onFriends}>뭉치 친구들 →</button>
          </span>
        </div>
      </section>
    </main>
  )
}
