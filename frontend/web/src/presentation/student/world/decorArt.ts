import { DECOR_GRID, inDecorGrid } from '../../../domain/retention.ts'
import type { DecorSurface } from '../../../domain/retention.ts'
import { BOARD, DESK_X, DESK_Z, DOOR, MAT_SIZE, MATS, onFloor, ROOM, RUG, SHELF, WARDROBE, WINDOW_Z } from './roomArt.ts'
import type { Face } from './roomArt.ts'
import { decorOf } from './roomAssets.ts'
import { bigLeavesBg, bookCoverBg, cactusBg, clockFaceBg, decorBg, decorColor, PAGES_BG, pictureBg, plantLeavesBg, soilBg } from './decorDraw.ts'

/**
 * 방 소품 칸(격자) ↔ 방 좌표와 방 소품 그림(#705, core #723 칸 계약안).
 * 바닥: 칸 80×75, col 0 = 왼쪽 벽 쪽(x -560), row 0 = 뒷벽 쪽(z -300). 화면을 채우려고 늘린 앞·오른쪽 바닥까지(17×13).
 * 뒷벽: 칸 80×86, col 0 = 왼쪽(x -560), row 0 = 위(y -516, 방 높이 430보다 한 줄 위까지 보임). 16×6.
 * 왼쪽 벽: 칸 75×86, col 0 = 뒷벽 쪽 구석(z -300), row 0 = 위. 11×6.
 */
const { W, D } = ROOM
export const CELL = { floor: { w: 80, d: 75 }, wall: { w: 80, h: 86 }, left: { w: 75, h: 86 } } as const
const WALL_TOP = -516

type Rect = [number, number, number, number]
/** 칸(기준 칸 + 크기)이 차지하는 영역. 바닥은 [x1, x2, z1, z2], 뒷벽은 [x1, x2, y1, y2], 왼쪽 벽은 [z1, z2, y1, y2] */
export function cellRect(surface: DecorSurface, col: number, row: number, w = 1, h = 1): Rect {
  if (surface === 'FLOOR') return [-W / 2 + col * CELL.floor.w, -W / 2 + (col + w) * CELL.floor.w, -D / 2 + row * CELL.floor.d, -D / 2 + (row + h) * CELL.floor.d]
  if (surface === 'WALL_BACK') return [-W / 2 + col * CELL.wall.w, -W / 2 + (col + w) * CELL.wall.w, WALL_TOP + row * CELL.wall.h, WALL_TOP + (row + h) * CELL.wall.h]
  return [-D / 2 + col * CELL.left.w, -D / 2 + (col + w) * CELL.left.w, WALL_TOP + row * CELL.left.h, WALL_TOP + (row + h) * CELL.left.h]
}
const overlaps = (a: Rect, b: Rect) => Math.min(a[1], b[1]) - Math.max(a[0], b[0]) > 8 && Math.min(a[3], b[3]) - Math.max(a[2], b[2]) > 8

/**
 * 가구·발판·창문·추억의 벽·문이 있어 방 소품을 놓을 수 없는 영역(웹이 검사, #723).
 * 갈 곳 앞 발판은 비워 둔다(문 앞은 문 발판이 덮음). 방 가운데(뭉치 출발 자리)는 밟는 소품(러그 등)은 놓을 수 있고 선 소품은 못 놓는다(placeProblem).
 */
/** 추억의 벽 게시판(뒷벽)·창문과 커튼·봉(왼쪽 벽). 줄 조명처럼 drape인 소품은 여기에 걸 수 있다 */
const BOARD_RECT: Rect = [BOARD.x - BOARD.w / 2, BOARD.x + BOARD.w / 2, BOARD.y - BOARD.h / 2, BOARD.y + BOARD.h / 2]
const WINDOW_RECTS: Rect[] = [
  [WINDOW_Z - 110, WINDOW_Z + 110, -385, -215],
  [WINDOW_Z - 166, WINDOW_Z - 110, -395, -165],
  [WINDOW_Z + 110, WINDOW_Z + 166, -395, -165],
  [WINDOW_Z - 180, WINDOW_Z + 180, -403, -393],
]
const DRAPE_OK = new Set<Rect>([BOARD_RECT, ...WINDOW_RECTS])
const BLOCKED: Record<DecorSurface, Rect[]> = {
  FLOOR: [
    [SHELF.x - SHELF.w / 2, SHELF.x + SHELF.w / 2, SHELF.z - SHELF.d / 2, SHELF.z + SHELF.d / 2],
    [WARDROBE.x - 110, WARDROBE.x + 110, -D / 2, WARDROBE.z + 65],
    [DESK_X - 80, DESK_X + 80, DESK_Z - 110, DESK_Z + 110],
    ...MATS.map((m): Rect => [m.x - MAT_SIZE.w / 2, m.x + MAT_SIZE.w / 2, m.z - MAT_SIZE.d / 2, m.z + MAT_SIZE.d / 2]),
  ],
  WALL_BACK: [
    BOARD_RECT,
    [WARDROBE.x - 110, WARDROBE.x + 110, -370, 0],
    [SHELF.x - SHELF.w / 2, SHELF.x + SHELF.w / 2, -SHELF.h, 0],
    [DOOR.x - DOOR.w / 2, DOOR.x + DOOR.w / 2, -DOOR.h, 0],
  ],
  WALL_LEFT: [
    ...WINDOW_RECTS,
    [DESK_Z - 110, DESK_Z + 110, -125, 0],
    [SHELF.z - SHELF.d / 2, SHELF.z + SHELF.d / 2, -SHELF.h, 0],
  ],
}
/** 그 칸이 막혔나. assetKey를 주면 그 소품이 걸 수 있는 곳(추억의 벽·창문 위)은 막힌 칸에서 뺀다 */
export const isBlockedCell = (surface: DecorSurface, col: number, row: number, assetKey?: string | null) => {
  const r = cellRect(surface, col, row)
  const drape = !!decorOf(assetKey)?.drape
  return BLOCKED[surface].some((b) => !(drape && DRAPE_OK.has(b)) && overlaps(r, b))
}
/** 추억의 벽·창문 위에 걸린 칸인가(그림을 액자·커튼보다 앞에 그린다) */
const onBoard = (r: Rect) => overlaps(r, BOARD_RECT)
const onWindow = (r: Rect) => WINDOW_RECTS.some((w) => overlaps(r, w))

/** 방 소품이 놓일 수 있는 면(벽 소품은 두 벽 중 아무 데나) */
export const surfacesFor = (assetKey: string | null | undefined): DecorSurface[] => {
  const d = decorOf(assetKey)
  if (!d) return []
  return d.kind === 'WALL' ? ['WALL_BACK', 'WALL_LEFT'] : ['FLOOR']
}
type Placed = { surface: DecorSurface; col: number; row: number; assetKey: string }
/** 그 방 소품이 차지하는 칸들(그림 목록 크기, 기준 칸에서 오른쪽·아래로) */
export const cellsOf = (p: Placed) => {
  const [w, h] = decorOf(p.assetKey)?.cells ?? [1, 1]
  const out: { col: number; row: number }[] = []
  for (let dc = 0; dc < w; dc++) for (let dr = 0; dr < h; dr++) out.push({ col: p.col + dc, row: p.row + dr })
  return out
}
/**
 * 방에 그려도 되는 놓인 방 소품인지(#723 "그리지 않을 것"): 그림 목록에 있고, 맞는 면이고, 범위 안이며, 막힌 칸이 아니고,
 * 앞서 그린 소품과 겹치지 않는 것. 가구 배치가 바뀌어 막힌 칸에 있는 소품도 여기서 빠진다.
 */
export function drawableDecor<T extends Placed>(spots: T[]): T[] {
  const taken = new Set<string>()
  return spots.filter((p) => {
    if (!surfacesFor(p.assetKey).includes(p.surface)) return false
    const cells = cellsOf(p)
    if (cells.some((c) => !inDecorGrid(p.surface, c.col, c.row) || isBlockedCell(p.surface, c.col, c.row, p.assetKey) || taken.has(`${p.surface}:${c.col}:${c.row}`))) return false
    cells.forEach((c) => taken.add(`${p.surface}:${c.col}:${c.row}`))
    return true
  })
}
/** 뭉치가 지나가지 못하는 바닥 방 소품 영역(화분처럼 선 것만, 러그는 밟고 지나감) */
export function decorFloorBlocks(spots: Placed[]): Rect[] {
  return spots.flatMap((p) => {
    const d = decorOf(p.assetKey)
    if (!d || !d.solid || p.surface !== 'FLOOR') return []
    const [w, h] = d.cells
    return [cellRect('FLOOR', p.col, p.row, w, h)]
  })
}
const BODY = 30
/** 걷기 막힘(useRoomWalk blocked): 선 방 소품 둘레 */
export const blockedByDecor = (rects: Rect[]) => (x: number, z: number) =>
  rects.some(([x1, x2, z1, z2]) => x > x1 - BODY && x < x2 + BODY && z > z1 - BODY && z < z2 + BODY)

/**
 * 뭉치가 출발 자리(방 가운데)에서 갈 곳 앞 발판 여섯 곳에 모두 갈 수 있는지(#705 길 막힘). 바닥을 20 간격 점으로 보고 넓이 우선 탐색.
 * 놓기 전에 이 검사를 통과하지 못하면 그 자리에 놓지 못한다.
 */
export function allMatsReachable(rects: Rect[]) {
  const blocked = blockedByDecor(rects)
  const step = 20
  const x0 = -W / 2, x1 = W / 2 + 280, z0 = -D / 2, z1 = D / 2 + 380
  const key = (x: number, z: number) => `${x},${z}`
  const ok = (x: number, z: number) => onFloor(x, z) && !blocked(x, z)
  const snap = (v: number, o: number) => o + Math.round((v - o) / step) * step
  const start = { x: snap(RUG.x, x0), z: snap(RUG.z, z0) }
  if (!ok(start.x, start.z)) return false
  const seen = new Set([key(start.x, start.z)])
  const queue = [start]
  while (queue.length) {
    const p = queue.shift()!
    for (const [dx, dz] of [[step, 0], [-step, 0], [0, step], [0, -step]]) {
      const n = { x: p.x + dx, z: p.z + dz }
      if (n.x < x0 || n.x > x1 || n.z < z0 || n.z > z1 || seen.has(key(n.x, n.z)) || !ok(n.x, n.z)) continue
      seen.add(key(n.x, n.z))
      queue.push(n)
    }
  }
  // 발판 가운데 가까운 점 하나라도 닿으면 갈 수 있다
  return MATS.every((m) => {
    for (let dx = -40; dx <= 40; dx += step) for (let dz = -40; dz <= 40; dz += step)
      if (seen.has(key(snap(m.x + dx, x0), snap(m.z + dz, z0)))) return true
    return false
  })
}

// ---------- 입체 소품(사용자 의견 2026-11-17 "방은 3D인데 소품은 너무 2D"): 가구처럼 상자로 세운다 ----------
const SHADOW = 'radial-gradient(closest-side, rgba(31,78,107,.28), rgba(31,78,107,0))'
const GLOW = 'radial-gradient(closest-side, rgba(255,230,120,.55), rgba(255,230,120,0))'
/** 바닥·뒷벽 방향 상자(앞면 +z, 옆면 +x, 윗면). y0 = 바닥(아래) 높이 */
function boxZ(out: Face[], key: string, x: number, z: number, w: number, d: number, h: number, y0: number, front: string, side: string, top?: string, radius?: string) {
  const ex: Partial<Face> = radius ? { radius } : {}
  out.push({ key: `${key}-f`, w, h, tf: `translate3d(${x}px,${y0 - h / 2}px,${z + d / 2}px)`, bg: front, ...ex })
  out.push({ key: `${key}-s`, w: d, h, tf: `translate3d(${x + w / 2}px,${y0 - h / 2}px,${z}px) rotateY(90deg)`, bg: side, ...ex })
  if (top) out.push({ key: `${key}-t`, w, h: d, tf: `translate3d(${x}px,${y0 - h}px,${z}px) rotateX(90deg)`, bg: top, ...ex })
}
/** 왼쪽 벽 방향 상자(앞면 +x = 방 안쪽, 옆면 +z = 방 앞쪽, 윗면). w = 벽에서 나온 길이, along = 벽을 따라간 길이 */
function boxX(out: Face[], key: string, x: number, z: number, w: number, along: number, h: number, y0: number, front: string, side: string, top?: string) {
  out.push({ key: `${key}-f`, w: along, h, tf: `translate3d(${x + w / 2}px,${y0 - h / 2}px,${z}px) rotateY(90deg)`, bg: front })
  out.push({ key: `${key}-s`, w, h, tf: `translate3d(${x}px,${y0 - h / 2}px,${z + along / 2}px)`, bg: side })
  if (top) out.push({ key: `${key}-t`, w, h: along, tf: `translate3d(${x}px,${y0 - h}px,${z}px) rotateX(90deg)`, bg: top })
}
/** 엇갈려 세운 그림판 두 장(잎·선인장 몸통). yBottom = 그림판 아래 높이 */
function crossed(out: Face[], key: string, x: number, z: number, w: number, h: number, yBottom: number, bg: string) {
  for (const rot of [0, 90]) out.push({ key: `${key}-${rot}`, w, h, tf: `translate3d(${x}px,${yBottom - h / 2}px,${z}px) rotateY(${rot}deg)`, bg, border: 'none' })
}
/** 화분(똑바른 몸통 + 조금 넓은 테두리, 윗면 흙). 테두리 위 높이를 돌려준다 */
function pot(out: Face[], key: string, x: number, z: number, bw: number, bh: number, pal: Record<string, string>) {
  const rw = bw + 8, rh = 11
  boxZ(out, `${key}-body`, x, z, bw, bw, bh, 0, pal.pot, pal.pot2)
  boxZ(out, `${key}-rim`, x, z, rw, rw, rh, -bh, pal.pot2, pal.pot2)
  out.push({ key: `${key}-soil`, w: rw, h: rw, tf: `translate3d(${x}px,${-bh - rh}px,${z}px) rotateX(90deg)`, bg: soilBg(pal.pot2), border: 'none' })
  return -bh - rh
}
/** 입체로 세우는 소품의 면들(없으면 null = 그림판·바닥·벽 그림) */
function buildSolid(p: Placed & { color?: string | null }, r: Rect): Face[] | null {
  const pal = decorColor(p.assetKey, p.color)?.pal ?? {}
  const k = `decor-${p.surface}-${p.col}-${p.row}`
  const out: Face[] = []
  if (p.surface === 'FLOOR') {
    const x = (r[0] + r[1]) / 2, z = (r[2] + r[3]) / 2
    const shadow = (w: number, d: number) => out.push({ key: `${k}-sh`, w, h: d, tf: `translate3d(${x}px,-1.5px,${z}px) rotateX(90deg)`, bg: SHADOW, border: 'none', radius: '50%' })
    switch (p.assetKey) {
      case 'room/decor-plant.svg': { shadow(70, 30); const top = pot(out, k, x, z, 46, 36, pal); crossed(out, `${k}-leaf`, x, z, 100, 80, top + 12, plantLeavesBg()); return out }
      case 'room/decor-plant-big.svg': { shadow(90, 36); const top = pot(out, k, x, z, 54, 42, pal); crossed(out, `${k}-leaf`, x, z, 160, 152, top + 10, bigLeavesBg()); return out }
      case 'room/decor-cactus.svg': { shadow(66, 28); const top = pot(out, k, x, z, 44, 32, pal); crossed(out, `${k}-body`, x, z, 92, 90, top + 8, cactusBg(pal)); return out }
      case 'room/decor-lamp.svg':
        out.push({ key: `${k}-glow`, w: 130, h: 80, tf: `translate3d(${x}px,-1.2px,${z}px) rotateX(90deg)`, bg: GLOW, border: 'none', radius: '50%' })
        boxZ(out, `${k}-base`, x, z, 44, 44, 9, 0, '#8A93A3', '#6E7684', '#A3ABB9')
        boxZ(out, `${k}-pole`, x, z, 11, 11, 120, -9, '#8A93A3', '#6E7684')
        // 갓: 아래 넓은 상자 + 위 좁은 상자(위가 좁은 갓 모양), 아래쪽에 밝은 띠
        boxZ(out, `${k}-shade`, x, z, 66, 66, 30, -116, `linear-gradient(transparent 70%, rgba(255,246,201,.9) 70%), ${pal.shade}`, pal.shade2, pal.shade)
        boxZ(out, `${k}-shade2`, x, z, 44, 44, 16, -146, pal.shade, pal.shade2, pal.shade)
        return out
      case 'room/decor-books.svg':
        shadow(86, 40)
        boxZ(out, `${k}-b1`, x, z, 74, 52, 17, 0, bookCoverBg(pal.b1), PAGES_BG, pal.b1)
        boxZ(out, `${k}-b2`, x + 4, z - 2, 64, 46, 17, -17, bookCoverBg(pal.b2), PAGES_BG, pal.b2)
        boxZ(out, `${k}-b3`, x - 3, z + 1, 70, 48, 17, -34, bookCoverBg(pal.b3), PAGES_BG, pal.b3)
        return out
      case 'room/decor-beanbag.svg':
        shadow(150, 70)
        // 앉는 부분 + 뒤에 붙은 등받이(모서리를 작게 둥글려 면이 따로 놀지 않게)
        boxZ(out, `${k}-seat`, x, z + 8, 136, 54, 30, 0, pal.bag, pal.bag2, `radial-gradient(ellipse at 40% 45%, rgba(255,255,255,.5) 0 16%, transparent 17%), ${pal.bag}`, '10px')
        boxZ(out, `${k}-back`, x, z - 24, 136, 22, 56, 0, `linear-gradient(rgba(255,255,255,.35) 0 18%, transparent 18%), ${pal.bag}`, pal.bag2, pal.bag, '10px')
        return out
      default:
        return null
    }
  }
  // 벽에 거는 입체 소품: 벽에서 조금 떨어뜨려 두께를 준다(추억의 벽·창문 위면 그 앞으로)
  const back = p.surface === 'WALL_BACK'
  const cx = (r[0] + r[1]) / 2, cy = (r[2] + r[3]) / 2
  const base = back ? (onBoard(r) ? BOARD.z + 8 : -D / 2) : -W / 2 + (onWindow(r) ? 10 : 0)
  const at = (offset: number) => (back ? `translate3d(${cx}px,${cy}px,${base + offset}px)` : `translate3d(${base + offset}px,${cy}px,${cx}px) rotateY(90deg)`)
  switch (p.assetKey) {
    case 'room/decor-clock.svg':
      out.push({ key: `${k}-back`, w: 70, h: 70, tf: at(3), bg: pal.rim, radius: '50%' })
      out.push({ key: `${k}-face`, w: 70, h: 70, tf: at(11), bg: clockFaceBg(pal.rim), border: 'none', radius: '50%' })
      return out
    case 'room/decor-picture.svg': {
      const w = 70, h = 64, d = 9
      if (back) boxZ(out, `${k}-frame`, cx, base + d / 2, w, d, h, cy + h / 2, pictureBg(pal.frame), pal.frame, pal.frame)
      else boxX(out, `${k}-frame`, base + d / 2, cx, d, w, h, cy + h / 2, pictureBg(pal.frame), pal.frame, pal.frame)
      return out
    }
    case 'room/decor-shelf.svg': {
      const len = 150, d = 30, y = cy + 26
      const plank = (key: string, along: number, a: number, dd: number, hh: number, y0: number, front: string, side: string, top: string) =>
        back ? boxZ(out, key, cx + a, base + dd / 2 + 2, along, dd, hh, y0, front, side, top) : boxX(out, key, base + dd / 2 + 2, cx - a, dd, along, hh, y0, front, side, top)
      plank(`${k}-plank`, len, 0, d, 10, y, pal.wood, pal.wood2, pal.wood)
      plank(`${k}-pot`, 20, -42, 18, 18, y - 10, '#E28D5B', '#C9744A', '#7A5230')
      plank(`${k}-bk1`, 12, 30, 22, 30, y - 10, '#7FC8D8', '#5BAFC2', '#7FC8D8')
      plank(`${k}-bk2`, 12, 44, 22, 36, y - 10, '#FFD84D', '#F2B21E', '#FFD84D')
      const lx = back ? cx - 42 : base + 12, lz = back ? base + 12 : cx + 42
      for (const rot of [0, 90]) out.push({ key: `${k}-lf${rot}`, w: 40, h: 32, tf: `translate3d(${lx}px,${y - 28 - 16}px,${lz}px) rotateY(${rot}deg)`, bg: plantLeavesBg(), border: 'none' })
      return out
    }
    default:
      return null
  }
}
// ---------- 그림 ----------
/**
 * 놓인 방 소품을 방 그림 면으로(내 방·친구 방). 서 있는 소품은 화면을 보는 그림판(faceCamera, 뭉치와 같은 방식) + 바닥 그림자,
 * 까는 소품은 바닥에 붙인 그림, 거는 소품은 벽에 붙인 그림. 그림·색은 decorDraw.ts
 */
export function decorFaces(spots: (Placed & { color?: string | null })[], faceCamera: (x: number, y: number, z: number) => string): Face[] {
  const faces: Face[] = []
  for (const p of spots) {
    const d = decorOf(p.assetKey)
    if (!d) continue
    const [w, h] = d.cells
    const k = `decor-${p.surface}-${p.col}-${p.row}`
    const r = cellRect(p.surface, p.col, p.row, w, h)
    const bg = decorBg(p.assetKey, p.color, d.stand ? 'contain' : '100% 100%')
    const solid = buildSolid(p, r)
    if (solid) { faces.push(...solid); continue }
    if (p.surface === 'FLOOR' && d.stand) {
      const [sw, sh] = d.stand
      const x = (r[0] + r[1]) / 2, z = (r[2] + r[3]) / 2
      faces.push({ key: `${k}-shadow`, w: sw * 0.8, h: 36, tf: `translate3d(${x}px,-1.5px,${z}px) rotateX(90deg)`, bg: 'radial-gradient(closest-side, rgba(31,78,107,.28), rgba(31,78,107,0))', border: 'none', radius: '50%' })
      faces.push({ key: k, w: sw, h: sh, tf: faceCamera(x, -sh / 2, z), bg, border: 'none' })
    } else if (p.surface === 'FLOOR') {
      const x = (r[0] + r[1]) / 2, z = (r[2] + r[3]) / 2
      faces.push({ key: k, w: r[1] - r[0] - 10, h: r[3] - r[2] - 10, tf: `translate3d(${x}px,-1.4px,${z}px) rotateX(90deg)`, bg, border: 'none' })
    } else {
      const y = (r[2] + r[3]) / 2
      if (p.surface === 'WALL_BACK') {
        // 추억의 벽 위면 액자(BOARD.z + 4)보다 앞에 그려 액자 위로 늘어지게
        const z = onBoard(r) ? BOARD.z + 12 : -D / 2 + 3
        faces.push({ key: k, w: r[1] - r[0], h: r[3] - r[2], tf: `translate3d(${(r[0] + r[1]) / 2}px,${y}px,${z}px)`, bg, border: 'none' })
      } else {
        faces.push({ key: k, w: r[1] - r[0], h: r[3] - r[2], tf: `translate3d(${-W / 2 + (onWindow(r) ? 12 : 3)}px,${y}px,${(r[0] + r[1]) / 2}px) rotateY(90deg)`, bg, border: 'none' })
      }
    }
  }
  return faces
}
export { DECOR_GRID }

// ---------- 놓기(#705 방 꾸미기 서랍 "방 소품") ----------
/**
 * 그 자리에 놓을 수 없는 까닭(놓을 수 있으면 null). 웹이 보는 규칙(#723): 맞는 면, 칸 범위, 막힌 칸, 다른 소품과 겹침, 뭉치 길.
 * skip: 옮기는 중인 소품(자기 자리는 겹침에서 뺌)의 순서. 개수 상한·가진 개수는 부르는 쪽이 본다.
 */
export function placeProblem(placed: Placed[], skip: number | null, cand: Placed): string | null {
  if (!surfacesFor(cand.assetKey).includes(cand.surface)) return decorOf(cand.assetKey)?.kind === 'WALL' ? '벽에 거는 소품이에요.' : '바닥에 놓는 소품이에요.'
  const cells = cellsOf(cand)
  if (cells.some((c) => !inDecorGrid(cand.surface, c.col, c.row))) return '방 끝을 넘어가요.'
  if (cells.some((c) => isBlockedCell(cand.surface, c.col, c.row, cand.assetKey))) return '가구나 창문이 있는 자리예요.'
  const taken = new Set(placed.flatMap((p, i) => (i === skip || p.surface !== cand.surface ? [] : cellsOf(p).map((c) => `${c.col}:${c.row}`))))
  if (cells.some((c) => taken.has(`${c.col}:${c.row}`))) return '다른 방 소품과 겹쳐요.'
  if (decorOf(cand.assetKey)?.solid && cand.surface === 'FLOOR') {
    // 뭉치 출발 자리(방 가운데)에는 선 소품을 못 놓는다(들어오면 뭉치가 소품 안에 서게 됨)
    if (blockedByDecor(decorFloorBlocks([cand]))(RUG.x, RUG.z)) return '뭉치가 서 있는 자리예요.'
    const others = placed.filter((_, i) => i !== skip)
    if (!allMatsReachable(decorFloorBlocks([...others, cand]))) return '뭉치가 지나갈 길을 막아요.'
  }
  return null
}
/** 놓을 수 있는 기준 칸 모두(방에 초록 칸으로 보임) */
export function placeableCells(placed: Placed[], skip: number | null, assetKey: string) {
  const out: { surface: DecorSurface; col: number; row: number }[] = []
  for (const surface of surfacesFor(assetKey)) {
    const { cols, rows } = DECOR_GRID[surface]
    for (let col = 0; col < cols; col++) for (let row = 0; row < rows; row++)
      if (!placeProblem(placed, skip, { surface, col, row, assetKey })) out.push({ surface, col, row })
  }
  return out
}
/** [놓기]를 눌렀을 때 처음 놓을 자리: 바닥은 러그 앞, 벽은 추억의 벽 위쪽에서 가까운 칸 */
export function firstPlace(placed: Placed[], assetKey: string) {
  const cells = placeableCells(placed, null, assetKey)
  if (!cells.length) return null
  const want = decorOf(assetKey)?.kind === 'WALL' ? { surface: 'WALL_BACK' as DecorSurface, x: BOARD.x, y: -430 } : { surface: 'FLOOR' as DecorSurface, x: RUG.x, y: RUG.z + 160 }
  const dist = (c: { surface: DecorSurface; col: number; row: number }) => {
    const r = cellRect(c.surface, c.col, c.row)
    return (c.surface === want.surface ? 0 : 1e6) + Math.hypot((r[0] + r[1]) / 2 - want.x, (r[2] + r[3]) / 2 - want.y)
  }
  return [...cells].sort((a, b) => dist(a) - dist(b))[0]
}
/** 화살표로 한 칸 옮길 때의 방향(화면 기준): 왼쪽 벽은 화면 왼쪽이 방 앞(col이 커짐) */
export function stepCell(surface: DecorSurface, dir: 'left' | 'right' | 'up' | 'down') {
  const flip = surface === 'WALL_LEFT' ? -1 : 1
  return { left: { dc: -1 * flip, dr: 0 }, right: { dc: 1 * flip, dr: 0 }, up: { dc: 0, dr: -1 }, down: { dc: 0, dr: 1 } }[dir]
}
/** 칸(들)을 덮는 방 그림 면 자리(놓기 칸 표시·고른 소품 테두리용) */
export function cellPlane(surface: DecorSurface, col: number, row: number, w = 1, h = 1) {
  const r = cellRect(surface, col, row, w, h)
  const cx = (r[0] + r[1]) / 2, cy = (r[2] + r[3]) / 2
  if (surface === 'FLOOR') return { w: r[1] - r[0], h: r[3] - r[2], tf: `translate3d(${cx}px,-3px,${cy}px) rotateX(90deg)` }
  if (surface === 'WALL_BACK') return { w: r[1] - r[0], h: r[3] - r[2], tf: `translate3d(${cx}px,${cy}px,${onBoard(r) ? BOARD.z + 16 : -D / 2 + 6}px)` }
  return { w: r[1] - r[0], h: r[3] - r[2], tf: `translate3d(${-W / 2 + (onWindow(r) ? 16 : 6)}px,${cy}px,${cx}px) rotateY(90deg)` }
}
