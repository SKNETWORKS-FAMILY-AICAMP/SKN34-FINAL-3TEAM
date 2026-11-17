import type { CSSProperties } from 'react'
import { floorOf, floorPaint, skinOf, wallpaperOf } from './roomAssets.ts'
import type { RoomSlot } from './roomAssets.ts'

/**
 * 내 방 그림(#648, 시안 MyPage의 그림체를 방 안 시점으로). CSS 3D 면(div)으로 방·가구를 세운다.
 * 바닥 가운데가 원점이고 y는 아래로 +. 벽지는 착용 배경(BACKGROUND), 가구 색은 착용 가구 스킨(DESK·WALL·WARDROBE).
 * 2026-11-16(사용자 결정): 방 가운데(뭉치 출발 자리)를 둘러싸고 갈 곳 6개 — 뒷벽 추억의 벽(가운데)·옷장(오른쪽)·문(더 오른쪽),
 * 왼쪽 벽 창문과 그 앞 책상, 앞 왼쪽 책장. 갈 곳 앞에는 둥근 발판이 있다. 장식 화분은 뺐다(사용자 결정 2026-11-17, 화분은 방 소품으로 사서 놓음 #705).
 * 세트: 벽지 → 벽·기본 바닥·커튼, 책상 스킨 → 책상·책장, 옷장 스킨 → 옷장·문, 추억의 벽 스킨 → 게시판·액자 테두리. 원래 러그 그림은 뺐다(사용자 결정 2026-11-17, 러그는 방 소품으로 사서 깖 #705).
 */
export const ROOM = { W: 1120, D: 600, H: 430, T: 26 } as const
const { W, D, H, T } = ROOM
/**
 * 방 안 시점(사용자 의견 2026-11-15 "디오라마 말고 창에 빈칸 없이 가득", 그림체는 그대로): 바닥은 앞·오른쪽으로, 벽은 위·앞·오른쪽으로
 * 창 밖까지 늘려 방 바깥(상자 테두리·바닥 두께·벽 윗면)이 보이지 않게 한다.
 */
export const EXT = { right: 1400, front: 900, up: 700 } as const
const LINE = '2px solid #1F4E6B'

export type Face = {
  key: string
  w: number
  h: number
  tf: string
  bg: string
  border?: string
  radius?: string
  shadow?: string
  /** 눌러서 걸어갈 수 있는 바닥 */
  floor?: boolean
  /** 이 면의 색을 바꾸는 착용 칸(세트). 고른 칸의 면만 잠깐 반짝이게 할 때 쓴다 */
  part?: RoomSlot
}
export const faceStyle = (f: Face): CSSProperties => ({
  width: f.w,
  height: f.h,
  marginLeft: -f.w / 2,
  marginTop: -f.h / 2,
  transform: f.tf,
  background: f.bg,
  border: f.border ?? LINE,
  borderRadius: f.radius ?? 0,
  boxShadow: f.shadow ?? 'none',
})

// ---------- 가구 자리 ----------
/** 추억의 벽 게시판 가운데(뒷벽) */
/*
 * 배치(사용자 의견 2026-11-16 "방 구조가 이게 맞아?": 책장이 창문을 막고 가구가 왼쪽 뒤에 몰려 오른쪽이 비었음 → 다시 잡음)
 * 뒷벽 왼쪽부터 책장 · 추억의 벽 · 옷장 · 문, 왼쪽 벽은 창문과 그 아래 책상만. 가운데는 뭉치 출발 자리.
 */
export const BOARD = { x: -70, y: -215, z: -D / 2 + 2, w: 520, h: 290 } as const
/** 책상(왼쪽 벽, 창문 아래에 붙임) */
export const DESK_X = -W / 2 + 90
export const DESK_Z = 140
/** 왼쪽 벽 창문 가운데(z): 책상 바로 위 */
export const WINDOW_Z = 140
/** 옷장(뒷벽 오른쪽) */
export const WARDROBE = { x: 300, z: -D / 2 + 66 } as const
/** 문(뒷벽, 옷장보다 더 오른쪽 빈 벽) */
export const DOOR = { x: 560, w: 140, h: 290 } as const
/** 책장(뒷벽 왼쪽 구석, 칸이 앞(+z)을 본다) */
export const SHELF = { x: -440, z: -D / 2 + 58, w: 200, d: 110, h: 250 } as const
/** 뭉치 출발 자리(방 가운데). 이름은 예전 러그 자리라서 RUG. 원래 러그 그림은 뺐다(사용자 결정 2026-11-17, 러그는 방 소품으로 사서 깖 #705) */
export const RUG = { x: 110, z: 130 } as const

/** 갈 곳 앞 발판: 뭉치가 올라서면 말풍선 */
export type MatId = 'desk' | 'window' | 'board' | 'wardrobe' | 'door' | 'shelf'
export const MATS: { id: MatId; x: number; z: number; color: string }[] = [
  { id: 'desk', x: -275, z: 100, color: '#FFE9A8' },
  { id: 'window', x: -275, z: 335, color: '#CFE6FA' },
  { id: 'board', x: -70, z: -170, color: '#FFF1D6' },
  { id: 'wardrobe', x: 300, z: -110, color: '#FBD3DF' },
  { id: 'door', x: 560, z: -150, color: '#DDF6D2' },
  { id: 'shelf', x: -440, z: -120, color: '#E8E0FF' },
]
export const MAT_SIZE = { w: 130, d: 84 } as const
/** 발판 가운데에서 이만큼 안이면 올라섰다고 본다 */
/** 발판 가운데에서 이만큼 안이면 그 가구 앞에 왔다고 본다(작은 발판 위에 꼭 서지 않아도 가까이 오면 말풍선, 사용자 의견 2026-11-16) */
export const MAT_RADIUS = 140

/** 캐릭터가 지나가지 못하는 가구: [x1, x2, z1, z2] 책상·옷장·책장 */
const BLOCKS = [
  [-W / 2, -W / 2 + 205, DESK_Z - 125, DESK_Z + 125],
  [WARDROBE.x - 120, WARDROBE.x + 120, -D / 2, WARDROBE.z + 65],
  [SHELF.x - SHELF.w / 2 - 10, SHELF.x + SHELF.w / 2 + 10, SHELF.z - SHELF.d / 2 - 10, SHELF.z + SHELF.d / 2 + 10],
]
const R = 40
/** 바닥 안쪽(벽에서 떨어짐)이고 가구에 겹치지 않는지. 화면 밖·단추 자리는 StudentRoom이 따로 본다 */
export const onFloor = (x: number, z: number) =>
  x > -W / 2 + 60 && z > -D / 2 + 50 && x < W / 2 + EXT.right - 60 && z < D / 2 + EXT.front - 60 &&
  !BLOCKS.some(([x1, x2, z1, z2]) => x > x1 - R && x < x2 + R && z > z1 - R && z < z2 + R)

/** 액자 6칸 자리(게시판 안 3칸 × 2줄)와 걸린 액자의 살짝 기운 각도 */
const COLS = [-165, 0, 165]
const ROWS = [-68, 68]
const TILTS = ['-1.5deg', '1deg', '-0.5deg', '1.5deg', '-1deg', '0.5deg']
export const slotTransform = (index: number, filled: boolean) =>
  `translate3d(${BOARD.x + COLS[index % 3]}px,${BOARD.y + ROWS[Math.floor(index / 3)]}px,${BOARD.z + 4}px) rotate(${filled ? TILTS[index] : '0deg'})`
export const boardTagTransform = `translate3d(${BOARD.x}px,${BOARD.y - BOARD.h / 2 - 22}px,${BOARD.z + 2}px)`

/**
 * 화면 좌표 계산(CSS 변환과 같은 식): 무대 1400×780, 방은 left 50%·top WORLD_TOP에서 scale(ws) rotateX(rx) rotateY(ry),
 * 무대 원근 2600(원점 50% 28%), 무대 scale(stageScale)·원점 위 가운데. 결과는 방 칸(holder) 왼쪽 위 기준 px.
 * 걷기 경계(보이는 바닥·단추 자리 빼기)에 쓴다.
 */
/** 방(world) 원점의 무대 높이 비율. CSS(.st-room-world top)도 이 값을 쓴다 */
export const WORLD_TOP = 0.66
/** 방을 보는 각도(돌려 보기는 끔, useRoomWalk CAN_ROTATE). 방 소품 칸이 PC 화면에 보이는지 계산에도 씀 */
export const ROOM_VIEW = { rx: -24, ry: -30 } as const
export function projectToHolder(x: number, y: number, z: number, v: { rx: number; ry: number; ws: number; stageScale: number; holderW: number }) {
  const ry = (v.ry * Math.PI) / 180
  const rx = (v.rx * Math.PI) / 180
  const X1 = x * Math.cos(ry) + z * Math.sin(ry)
  const Z1 = -x * Math.sin(ry) + z * Math.cos(ry)
  const Y2 = y * Math.cos(rx) - Z1 * Math.sin(rx)
  const Z2 = y * Math.sin(rx) + Z1 * Math.cos(rx)
  const px = 700 + X1 * v.ws
  const py = 780 * WORLD_TOP + Y2 * v.ws
  const f = 2600 / (2600 - Z2 * v.ws)
  const sx = 700 + (px - 700) * f
  const sy = 780 * 0.28 + (py - 780 * 0.28) * f
  return { x: v.holderW / 2 + (sx - 700) * v.stageScale, y: sy * v.stageScale }
}

/** floor: 바닥 그림 키(#705), 없거나 null이면 벽지 세트의 바닥 */
export type RoomLook = { wallpaper: string | null; floor?: string | null; desk: string | null; wall: string | null; wardrobe: string | null }
export function roomFaces(look: RoomLook, activeMat: MatId | null = null): Face[] {
  const wp = wallpaperOf(look.wallpaper)
  const desk = skinOf('DESK', look.desk)
  const dk = desk.faces
  const bd = skinOf('WALL', look.wall).faces
  const wardrobe = skinOf('WARDROBE', look.wardrobe)
  const wd = wardrobe.faces
  const faces: Face[] = []
  const plane = (key: string, w: number, h: number, tf: string, bg: string, ex: Partial<Face> = {}) =>
    faces.push({ key, w, h, tf, bg, ...ex })
  const box = (key: string, x: number, z: number, w: number, h: number, d: number, c: readonly string[], y0 = 0, front?: string, radius?: string, part?: RoomSlot) => {
    const ex: Partial<Face> = { ...(radius ? { radius } : {}), ...(part ? { part } : {}) }
    plane(`${key}-top`, w, d, `translate3d(${x}px,${y0 - h}px,${z}px) rotateX(90deg)`, c[0], ex)
    plane(`${key}-front`, w, h, `translate3d(${x}px,${y0 - h / 2}px,${z + d / 2}px)`, front ?? c[1], ex)
    plane(`${key}-side`, d, h, `translate3d(${x + w / 2}px,${y0 - h / 2}px,${z}px) rotateY(90deg)`, c[2], ex)
  }
  const shade = 'linear-gradient(rgba(15,59,54,.13), rgba(15,59,54,.13)), '
  // 바닥(누르면 걸어감): 고른 바닥(#705), 없으면 벽지 세트의 마루. 뒤·왼쪽 벽에서 시작해 앞·오른쪽은 창 밖까지
  const FW = W + EXT.right, FD = D + EXT.front, WH = H + EXT.up
  plane('floor', FW, FD, `translate3d(${EXT.right / 2}px,0px,${EXT.front / 2}px) rotateX(90deg)`, floorPaint(look.floor, look.wallpaper), { floor: true, border: 'none', part: floorOf(look.floor) ? 'FLOOR' : 'BACKGROUND' })
  // 벽(뒷벽·왼쪽 벽)도 위·앞·오른쪽으로 창 밖까지, 두 벽이 만나는 모서리 선만 남김
  plane('wall-back', FW + T, WH, `translate3d(${EXT.right / 2 - T / 2}px,${-WH / 2}px,${-D / 2}px)`, wp.paint, { border: 'none', part: 'BACKGROUND' })
  plane('wall-left', FD, WH, `translate3d(${-W / 2}px,${-WH / 2}px,${EXT.front / 2}px) rotateY(90deg)`, shade + wp.paint, { border: 'none', shadow: 'inset -2px 0 0 #1F4E6B', part: 'BACKGROUND' })
  // 걸레받이
  plane('base-back', FW, 22, `translate3d(${EXT.right / 2}px,-11px,${-D / 2 + 1}px)`, '#FFFFFF', { border: 'none', shadow: 'inset 0 2px 0 #1F4E6B' })
  plane('base-left', FD, 22, `translate3d(${-W / 2 + 1}px,-11px,${EXT.front / 2}px) rotateY(90deg)`, '#F1E6D2', { border: 'none', shadow: 'inset 0 2px 0 #1F4E6B' })
  // 왼쪽 벽 창문 + 양옆 커튼(벽지 세트 색)
  plane('window', 220, 170, `translate3d(${-W / 2 + 2}px,-300px,${WINDOW_Z}px) rotateY(90deg)`,
    'linear-gradient(90deg, transparent 47%, #FFFFFF 47% 53%, transparent 53%), linear-gradient(transparent 46%, #FFFFFF 46% 54%, transparent 54%), radial-gradient(circle at 75% 25%, #FFE9A8 16px, transparent 17px), #CFE6FA',
    { shadow: 'inset 0 0 0 9px #FFFFFF' })
  const curtain = `repeating-linear-gradient(90deg, rgba(255,255,255,.28) 0 6px, transparent 6px 16px), ${wp.curtain}`
  plane('curtain-l', 56, 230, `translate3d(${-W / 2 + 4}px,-280px,${WINDOW_Z - 138}px) rotateY(90deg)`, curtain, { radius: '0 0 18px 18px', part: 'BACKGROUND' })
  plane('curtain-r', 56, 230, `translate3d(${-W / 2 + 4}px,-280px,${WINDOW_Z + 138}px) rotateY(90deg)`, curtain, { radius: '0 0 18px 18px', part: 'BACKGROUND' })
  plane('curtain-rod', 360, 10, `translate3d(${-W / 2 + 5}px,-398px,${WINDOW_Z}px) rotateY(90deg)`, '#8A5A33', { radius: '5px' })
  // 추억의 벽 게시판(뒷벽 가운데)
  plane('board', BOARD.w, BOARD.h, `translate3d(${BOARD.x}px,${BOARD.y}px,${BOARD.z}px)`, bd[0],
    { border: '3px solid #1F4E6B', radius: '14px', shadow: `inset 0 0 0 10px ${bd[0]}, inset 0 0 0 13px ${bd[1]}`, part: 'WALL' })
  // 문(뒷벽, 옷장 세트 색): 문틀 + 문판(홈 두 칸) + 손잡이
  const [doorFrame, doorPanel, knob] = wardrobe.set
  plane('door-frame', DOOR.w + 24, DOOR.h + 12, `translate3d(${DOOR.x}px,${-(DOOR.h + 12) / 2}px,${-D / 2 + 1}px)`, doorFrame, { radius: '10px 10px 0 0', part: 'WARDROBE' })
  plane('door', DOOR.w, DOOR.h, `translate3d(${DOOR.x}px,${-DOOR.h / 2}px,${-D / 2 + 3}px)`,
    `radial-gradient(circle at 84% 54%, ${knob} 7px, transparent 8px), linear-gradient(transparent 10%, rgba(15,59,54,.12) 10% 44%, transparent 44% 52%, rgba(15,59,54,.12) 52% 90%, transparent 90%) 18px 0 / calc(100% - 36px) 100% no-repeat, ${doorPanel}`,
    { radius: '6px 6px 0 0', part: 'WARDROBE' })
  // 갈 곳 앞 발판: 평소에는 보이지 않고(발판이 러그 여러 개처럼 보여서, 사용자 의견 2026-11-16) 뭉치가 올라선 발판만 은은하게 빛남
  for (const m of MATS)
    if (m.id === activeMat)
      plane(`mat-${m.id}`, MAT_SIZE.w, MAT_SIZE.d, `translate3d(${m.x}px,-1.5px,${m.z}px) rotateX(90deg)`, 'radial-gradient(closest-side, rgba(255,216,77,.75), rgba(255,216,77,0))',
        { radius: '50%', border: 'none' })
  // 옷장: 벽(430) 높이의 약 86%. 가구·캐릭터 비율은 실제 비율(옷장 180cm·책상 75cm)에 가깝게(사용자 의견 2026-11-15 "가구 비율")
  box('wardrobe', WARDROBE.x, WARDROBE.z, 220, 370, 130, wd, 0,
    `radial-gradient(circle at 44% 50%, #3A2A20 5px, transparent 6px), radial-gradient(circle at 56% 50%, #3A2A20 5px, transparent 6px), linear-gradient(90deg, transparent 49.2%, #3A2A20 49.2% 50.8%, transparent 50.8%), ${wd[1]}`, undefined, 'WARDROBE')
  // 책상: 상판 + 다리 4 + 책 두 권·연필꽂이
  // 책상: 실제 비율(벽 430 ≈ 천장 2.4m, 1칸 ≈ 0.56cm)로 높이 약 70cm = 125(다리 109 + 상판 16), 상판 160×220.
  // 뭉치(140 ≈ 78cm)가 책상보다 조금 크게(사용자 의견 2026-11-16 "책상이 왜 이렇게 커"·"이 크기가 맞아?")
  box('desk', DESK_X, DESK_Z, 160, 16, 220, dk, -109, undefined, undefined, 'DESK')
  const leg = [dk[2], dk[2], dk[2]]
  ;[[-66, -98], [66, -98], [-66, 98], [66, 98]].forEach(([lx, lz], i) => box(`leg${i}`, DESK_X + lx, DESK_Z + lz, 14, 109, 14, leg, 0, undefined, undefined, 'DESK'))
  box('book1', DESK_X - 18, DESK_Z - 52, 50, 14, 36, ['#FFD84D', '#F2B21E', '#C98A12'], -125)
  box('book2', DESK_X - 14, DESK_Z - 52, 42, 12, 30, ['#7FC8D8', '#5BAFC2', '#3F8FA2'], -139)
  box('pencil', DESK_X + 26, DESK_Z + 60, 18, 36, 18, ['#9CCB8C', '#6FAE5F', '#4F8E40'], -125)
  // 책장(뒷벽 왼쪽 구석, 책상 세트 색): 앞(+z) 면에 칸 4줄과 책
  const sh = desk.set
  const shelves = `repeating-linear-gradient(transparent 0 52px, ${sh[2]} 52px 62px), ` +
    'repeating-linear-gradient(90deg, #E3533C 0 14px, #FFD84D 14px 26px, #7FC8D8 26px 40px, transparent 40px 50px, #9CCB8C 50px 62px, #F7AEC4 62px 74px, transparent 74px 96px)'
  box('shelf', SHELF.x, SHELF.z, SHELF.w, SHELF.h, SHELF.d, sh, 0,
    `linear-gradient(${sh[1]}, ${sh[1]}) 0 0 / 100% 10px no-repeat, ${shelves}, ${sh[1]}`, undefined, 'DESK')
  return faces
}
