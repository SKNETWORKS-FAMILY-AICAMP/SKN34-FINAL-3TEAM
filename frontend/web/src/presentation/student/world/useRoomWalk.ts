import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from 'react'
import type { FriendView } from './friendArt.ts'
import { MATS, onFloor, projectToHolder, ROOM, RUG } from './roomArt.ts'

/**
 * 캐릭터 걷기(바닥 누르기·방향키·스페이스 점프). 사용자 결정 2026-11-16으로 켬(기능명세 P27 문구도 고침).
 * 화면 안에서만 움직이고 자리는 저장하지 않는다. 보이는 바닥 안·가구 밖·방 위 단추 자리 밖에서만 선다.
 */
export const CAN_WALK = true
/** 걷는 빠르기(방 좌표/초): 갈 곳 사이가 1~2초쯤(230에서 올림, 사용자 의견 2026-11-16 "움직이는 속도 좀 빠르게") */
const SPEED = 380
/** 방 돌려 보기: 방 안 시점(벽·바닥이 창 밖까지)이라 돌리면 방 끝이 드러나 끔(사용자 의견 2026-11-15 "디오라마 말고") */
export const CAN_ROTATE = false
const START: { rx: number; ry: number } = { rx: -24, ry: -30 }
const MOVE_KEYS: Record<string, 'u' | 'd' | 'l' | 'r'> = {
  ArrowUp: 'u', KeyW: 'u', ArrowDown: 'd', KeyS: 'd', ArrowLeft: 'l', KeyA: 'l', ArrowRight: 'r', KeyD: 'r',
}
export const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

/**
 * 방 안 걷기·크기 맞추기(#709에서 내 방 StudentRoom에서 떼어 냄, 동작은 그대로). 내 방과 친구 방(놀러 가기)이 같이 쓴다.
 * - start: 뭉치 처음 자리(내 방은 러그, 친구 방은 문 앞)
 * - paused: 방 꾸미기 중처럼 걷기를 멈출 때(바닥 누르기·방향키 무시, 방 칸을 조금 더 줄임)
 * - blocked: 바닥·가구 말고 더 막을 곳(친구 방의 친구 뭉치 자리)
 */
export function useRoomWalk({ start = { x: RUG.x, z: RUG.z }, paused = false, blocked }: {
  start?: { x: number; z: number }
  paused?: boolean
  blocked?: (x: number, z: number) => boolean
} = {}) {
  // ---- 방 보기(돌리기·움직이기) 상태 ----
  const [view, setView] = useState({ rx: START.rx, ry: START.ry })
  const [dragging, setDragging] = useState(false)
  const [pos, setPos] = useState({ x: start.x, z: start.z })
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
    if (!onFloor(x, z) || blocked?.(x, z)) return false
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
  /** 그 자리에 설 수 있나(방 위 단추는 빼고 봄). 화면 크기를 잰 뒤에 맞다 */
  const canStand = (p: { x: number; z: number }) => standable(p.x, p.z, true)
  /** 걷지 않고 그 자리로 옮김(친구 방: 문 앞이 좁은 화면 밖이면 보이는 곳에서 들어옴) */
  const placeAt = (p: { x: number; z: number }) => { path.current = []; posRef.current = p; setPos(p) }
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
    if (!CAN_WALK || e.target !== e.currentTarget || paused) return
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
    if (justDragged.current || paused) return
    const { offsetX, offsetY } = e.nativeEvent
    walkTo({ x: offsetX - ROOM.W / 2, z: offsetY - ROOM.D / 2 })
  }
  const turn = (d: number) => setView((v) => ({ ...v, ry: clamp(v.ry + d, -50, -12) }))
  const faceCamera = (x: number, y: number, z: number) => `translate3d(${x}px,${y}px,${z}px) rotateY(${-view.ry}deg) rotateX(${-view.rx}deg)`

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
  }, [paused])
  // PC(901px 이상·창 높이 700px 이상)는 스크롤 없이 한 화면(사용자 의견 2026-11-15 "스크롤을 해야 하는 게 말이 안 돼"):
  // 방 칸은 칸 폭 전체 × 제목 아래 남은 높이. 방 안 시점이라 벽·바닥이 창 밖까지 이어져 높이에 맞춰 줄여도 양옆이 비지 않는다.
  // 좁은 화면은 문서 전체를 내려 보는 방식 그대로, 무대 폭을 1060으로 보고 크게(오른쪽 끝 문까지 보이는 한도, 2026-11-16)
  const oneScreen = Number.isFinite(fit.h)
  const holderH = oneScreen ? Math.max(paused ? 210 : 240, Math.min(fit.h, 780 * (fit.w / 1400))) : 780 * Math.min(1.2, fit.w / (fit.w < 700 ? 1060 : 1400))
  const scale = Math.max(0.2, Math.min(1.2, oneScreen ? Math.min(fit.w / 1400, holderH / 780) : fit.w / (fit.w < 700 ? 1060 : 1400)))
  // 방이 무대를 넉넉히 채우게(0.72에서 키움, 사용자 의견 2026-11-15 "너무 작아 보여")
  // 빈 벽 여백을 줄이게 더 당김(사용자 의견 2026-11-16 "여백이 너무 넓어")
  const worldScale = fit.w < 700 ? 0.92 : 1.0

  // 걷기 경계 계산용 지금 크기
  useLayoutEffect(() => { metrics.current = { ws: worldScale, stageScale: scale, holderW: fit.w, holderH } }, [worldScale, scale, fit.w, holderH])

  return {
    view, dragging, pos, facing, pose, moving, jumping, stageRef, holderRef, roomRef, drawerRef,
    fit, holderH, scale, worldScale, onKeyDown, onKeyUp, onBlur, onPointerDown, onFloorClick, turn, faceCamera, walkTo, canStand, placeAt,
  }
}
