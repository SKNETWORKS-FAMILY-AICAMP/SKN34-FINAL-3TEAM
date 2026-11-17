import type { CompanionId, FriendId } from '../../../domain/studentLook.ts'
import { COMPANIONS, companionToFriend, FRIENDS } from '../../../domain/studentLook.ts'
import type { FurnitureSlot } from '../../../domain/retention.ts'
import { frontEdge } from './friendArt.ts'

/**
 * 내 방 그림 리소스 표(#557, P27). 그림은 roomArt.ts, 이 파일은 assetKey·가격·위치 상수.
 * 관리자가 아이템을 등록할 때 아래 assetKey를 `look_item.asset_key`로 그대로 넣는다
 * (docs/report/retention-expansion.md 3.7).
 */
export const DEFAULT_WALLPAPER = 'room/wall-default.svg'

/**
 * 가구 스킨. faces는 3D 방의 [윗면, 앞면, 옆면] 색(시안 MyPage 값), swatch는 고르기 칸 색.
 * set은 같은 칸이 함께 바꾸는 가구 색(사용자 결정 2026-11-16 "세트"): 책상 스킨 → 책장, 옷장 스킨 → 문, 추억의 벽 스킨 → 액자 테두리
 */
type Skin = { assetKey: string; name: string; faces: [string, string, string]; swatch: string; set: [string, string, string] }
export const FURNITURE_SKINS: Record<FurnitureSlot, Skin[]> = {
  // 책상 + 책장(set: 책장 [윗면, 앞면, 옆면])
  DESK: [
    { assetKey: 'room/desk-wood.svg', name: '나무 책상', faces: ['#E2B07E', '#C98B55', '#A86E3E'], swatch: '#C98B55', set: ['#D9A46F', '#B97C48', '#9C6738'] },
    { assetKey: 'room/desk-mint.svg', name: '민트 책상', faces: ['#B9DEC2', '#8FBF9A', '#6FA57D'], swatch: '#8FBF9A', set: ['#A9D5B5', '#7FB38C', '#5F9A6E'] },
    { assetKey: 'room/desk-night.svg', name: '밤하늘 책상', faces: ['#4A42A0', '#2A2070', '#1E1858'], swatch: '#2A2070', set: ['#3E368E', '#2A2070', '#1E1858'] },
    { assetKey: 'room/desk-cherry.svg', name: '체리 책상', faces: ['#F2A7A0', '#D9776E', '#B85A52'], swatch: '#D9776E', set: ['#E99890', '#CC6A62', '#A84E47'] },
  ],
  // 추억의 벽(게시판): [판 색, 안쪽 테두리 색, 테두리 색], set: 액자 테두리 [나무 틀, 그림자, 선]
  WALL: [
    { assetKey: 'room/wall-cork.svg', name: '코르크 벽', faces: ['#D9B98A', '#B48F5E', '#B48F5E'], swatch: '#D9B98A', set: ['#8A5A33', '#3A2A20', '#1F4E6B'] },
    { assetKey: 'room/wall-wood.svg', name: '나무 벽', faces: ['#C98B55', '#9C6738', '#9C6738'], swatch: '#C98B55', set: ['#5E3B1E', '#3A2A20', '#1F4E6B'] },
    { assetKey: 'room/wall-pastel.svg', name: '구름 벽', faces: ['#E6F1FA', '#A9CBE6', '#A9CBE6'], swatch: '#E6F1FA', set: ['#FFFFFF', '#7FA6C6', '#1F4E6B'] },
    { assetKey: 'room/wall-star.svg', name: '별빛 벽', faces: ['#3E368E', '#FFD84D', '#FFD84D'], swatch: '#3E368E', set: ['#FFD84D', '#1E1858', '#1F4E6B'] },
  ],
  // 옷장 + 문(set: 문 [문틀, 문판, 손잡이])
  WARDROBE: [
    { assetKey: 'room/wardrobe-wood.svg', name: '나무 옷장', faces: ['#F2D9B6', '#E9C79B', '#C9A26F'], swatch: '#E9C79B', set: ['#C9A26F', '#E9C79B', '#3A2A20'] },
    { assetKey: 'room/wardrobe-sky.svg', name: '하늘 옷장', faces: ['#D4E9F7', '#B8D8EE', '#93BFDF'], swatch: '#B8D8EE', set: ['#93BFDF', '#B8D8EE', '#1F4E6B'] },
    { assetKey: 'room/wardrobe-berry.svg', name: '딸기 옷장', faces: ['#FBD3DF', '#F7AEC4', '#E28DA8'], swatch: '#F7AEC4', set: ['#E28DA8', '#F7AEC4', '#3A2A20'] },
    { assetKey: 'room/wardrobe-lemon.svg', name: '레몬 옷장', faces: ['#FFF0A8', '#FFDF6B', '#E8C23F'], swatch: '#FFDF6B', set: ['#E8C23F', '#FFDF6B', '#3A2A20'] },
  ],
}
/** 추가 스킨 해금값 기준안: 주간 최대 적립(약 125포인트)의 절반·한 주치 */
export const FURNITURE_SKIN_PRICES = [0, 60, 120]
export const skinOf = (slot: FurnitureSlot, assetKey: string | null | undefined) =>
  FURNITURE_SKINS[slot].find((s) => s.assetKey === assetKey) ?? FURNITURE_SKINS[slot][0]
export const furnitureSkinName = (slot: FurnitureSlot, assetKey: string | null) => skinOf(slot, assetKey).name

/** 내 방 착용 칸: 벽지(BACKGROUND) + 바닥(FLOOR, #705) + 가구 3칸 */
export type RoomSlot = 'BACKGROUND' | 'FLOOR' | FurnitureSlot
/**
 * 칸 하나를 바꾸면 함께 바뀌는 것(세트, 사용자 결정 2026-11-16). 꾸미기·방 꾸미기 칸 아래에 그대로 적어
 * "무엇이 어떻게 바뀌는지" 보이게 한다(사용자 의견 2026-11-16 "가독성이 없어").
 */
export const ROOM_SET_PARTS: Record<RoomSlot, string> = {
  // 바닥을 따로 고르지 않았으면 벽지 세트의 바닥이 깔린다(#704 확정: 바닥 착용 없음 = 벽지 세트 바닥)
  BACKGROUND: '벽지 · 커튼 · 기본 바닥',
  FLOOR: '바닥',
  DESK: '책상 · 책장',
  WALL: '추억의 벽 · 액자 테두리',
  WARDROBE: '옷장 · 문',
}

/**
 * 벽지(BACKGROUND 착용 아이템 = 방 벽지). 시안 MyPage의 CSS 무늬 그대로, 모르는 그림 키는 기본 벽지.
 * 기존 배경 아이템(별빛 배경)은 같은 assetKey로 "별밤" 벽지를 쓴다.
 */
/**
 * 벽지 세트: 벽 무늬 + 창문 커튼 색(사용자 결정 2026-11-16 "세트") + 바닥 마루 [판 색, 판 사이 줄 색]. 원래 러그 그림은 뺐다(사용자 결정 2026-11-17, 러그는 방 소품으로 사서 깖 #705).
 * 바닥은 서버 칸이 없어 벽지 세트에 넣었다(사용자 결정 2026-11-16 "바닥 설정도 있어야 해" → 지금은 세트, 바닥만 따로 고르는 칸은 core FLOOR 칸으로)
 */
type Wallpaper = { name: string; swatch: string; paint: string; curtain: string; floor: [string, string] }
const dots = 'radial-gradient(circle at 6px 6px, rgba(255,255,255,.65) 2.6px, transparent 3.2px) 0 0 / 26px 26px'
export const WALLPAPERS: Record<string, Wallpaper> = {
  [DEFAULT_WALLPAPER]: { name: '민트 물방울', swatch: '#DDF1FF', paint: `${dots}, #DDF1FF`, curtain: '#FFD84D', floor: ['#E9D2A8', '#C9A877'] },
  'looks/bg-stars.svg': {
    name: '별밤',
    swatch: '#2A2070',
    paint: 'radial-gradient(circle at 22px 22px, #FFE45C 3.4px, transparent 4px) 0 0 / 84px 84px, radial-gradient(circle at 62px 58px, #FFFFFF 2px, transparent 2.6px) 0 0 / 84px 84px, #2A2070',
   
    curtain: '#7FC8D8',
    floor: ['#B98A5E', '#8E6440'],
  },
  // 시안 MyPage 벽지 무늬(목업 추가 아이템, 2026-11-16)
  'room/wall-cream.svg': {
    name: '크림 줄무늬', swatch: '#F6E3C8',
    paint: 'repeating-linear-gradient(90deg, rgba(255,255,255,.5) 0 14px, transparent 14px 36px), #F6E3C8', curtain: '#F7AEC4', floor: ['#F3E6CF', '#D8C29C'],
  },
  'room/wall-sky.svg': {
    name: '하늘 구름', swatch: '#CFE6FA',
    paint: 'radial-gradient(ellipse 46px 20px at 60px 46px, rgba(255,255,255,.85) 96%, transparent 100%) 0 0 / 170px 110px, #BFDDF5', curtain: '#FFFFFF', floor: ['#DCE3E8', '#AFBCC6'],
  },
}
export const wallpaperOf = (assetKey: string | null | undefined) => WALLPAPERS[assetKey ?? ''] ?? WALLPAPERS[DEFAULT_WALLPAPER]

/**
 * 바닥(FLOOR 착용 아이템, #705·core #704). 시안 MyPage 서랍의 바닥 세 가지를 방 그림체(CSS 무늬)로 옮겼다.
 * paint는 큰 방(방 단위 px), thumb은 고르기 칸 그림(작은 칸)용. 모르는 그림 키나 착용 없음은 벽지 세트의 바닥.
 * 관리자가 등록할 그림 키 = 아래 키(docs/report/retention-expansion.md 3.7 방식으로 알림).
 */
type Floor = { name: string; swatch: string; paint: string; thumb: string }
export const FLOORS: Record<string, Floor> = {
  'room/floor-wood.svg': {
    name: '나무 마루', swatch: '#C98B55',
    paint: 'repeating-linear-gradient(90deg, #DDA772 0 108px, #B5793F 108px 111px)',
    thumb: 'repeating-linear-gradient(90deg, #DDA772 0 10px, #B5793F 10px 11px)',
  },
  'room/floor-mint.svg': {
    name: '민트 타일', swatch: '#BFE6D3',
    paint: 'linear-gradient(90deg, #8FC9AE 0 4px, transparent 4px) 0 0 / 96px 96px, linear-gradient(#8FC9AE 0 4px, transparent 4px) 0 0 / 96px 96px, #CDEEDD',
    thumb: 'linear-gradient(90deg, #8FC9AE 0 1px, transparent 1px) 0 0 / 12px 12px, linear-gradient(#8FC9AE 0 1px, transparent 1px) 0 0 / 12px 12px, #CDEEDD',
  },
  'room/floor-carpet.svg': {
    name: '초록 카펫', swatch: '#8CC27C',
    paint: 'radial-gradient(circle at 12px 12px, rgba(255,255,255,.22) 2.4px, transparent 3px) 0 0 / 26px 26px, radial-gradient(circle at 25px 25px, rgba(47,110,60,.18) 2.4px, transparent 3px) 0 0 / 26px 26px, #8CC27C',
    thumb: 'radial-gradient(circle at 3px 3px, rgba(255,255,255,.3) 1px, transparent 1.4px) 0 0 / 7px 7px, #8CC27C',
  },
}
export const floorOf = (assetKey: string | null | undefined): Floor | undefined => FLOORS[assetKey ?? '']
/** 방 바닥 무늬: 고른 바닥, 없으면 벽지 세트의 바닥 마루 */
export function floorPaint(floor: string | null | undefined, wallpaper: string | null | undefined, small = false) {
  const f = floorOf(floor)
  if (f) return small ? f.thumb : f.paint
  const [plank, line] = wallpaperOf(wallpaper).floor
  return small ? `repeating-linear-gradient(90deg, ${plank} 0 10px, ${line} 10px 11px)` : `repeating-linear-gradient(90deg, ${plank} 0 108px, ${line} 108px 111px)`
}
/**
 * 방 소품(DECOR, #705·core #704). 같은 것을 여러 개 사서 내 방 칸에 놓는다(놓기는 core #723 칸 계약 뒤).
 * kind: 바닥에 놓는지 벽에 거는지, cells: 차지하는 칸 수 [가로, 세로](#723: 서버는 기준 칸만 저장하고 크기·겹침은 웹이 본다). 모두 기준안.
 * 관리자가 등록할 그림 키 = 아래 키. 목록에 없는 키는 그림을 그리지 않는다.
 */
export type DecorKind = 'FLOOR' | 'WALL'
/**
 * solid: 뭉치가 지나가지 못함(서 있는 것). 러그처럼 바닥에 깔리면 false
 * drape: 추억의 벽(게시판·액자)과 창문(커튼·봉) 위에도 걸 수 있음(사용자 의견·결정 2026-11-17). 액자·창문을 가리는 벽 소품은 false(기본)
 * stand: 바닥에 서는 소품의 그림판 크기 [가로, 높이](방 단위, 화면을 보는 그림판으로 그림). 없으면 바닥에 깔림
 * 색은 decorDraw.ts DECOR_COLORS(놓은 것마다 고름, core #723 color). 15가지·크기·색 모두 기준안(사용자 결정 2026-11-17 "여러 개, 색상이든 크기든")
 */
type Decor = { name: string; kind: DecorKind; cells: [number, number]; solid: boolean; drape?: boolean; stand?: [number, number] }
export const DECORS: Record<string, Decor> = {
  // 바닥에 서는 것
  'room/decor-plant.svg': { name: '작은 화분', kind: 'FLOOR', cells: [1, 1], solid: true, stand: [92, 110] },
  'room/decor-plant-big.svg': { name: '큰 화분', kind: 'FLOOR', cells: [1, 1], solid: true, stand: [154, 196] },
  'room/decor-cactus.svg': { name: '선인장', kind: 'FLOOR', cells: [1, 1], solid: true, stand: [90, 108] },
  'room/decor-lamp.svg': { name: '스탠드 조명', kind: 'FLOOR', cells: [1, 1], solid: true, stand: [104, 182] },
  'room/decor-doll.svg': { name: '뭉치 인형', kind: 'FLOOR', cells: [1, 1], solid: true, stand: [100, 100] },
  'room/decor-books.svg': { name: '쌓은 책', kind: 'FLOOR', cells: [1, 1], solid: true, stand: [92, 67] },
  'room/decor-beanbag.svg': { name: '쿠션 소파', kind: 'FLOOR', cells: [2, 1], solid: true, stand: [152, 98] },
  // 바닥에 까는 것
  'room/decor-rug.svg': { name: '동그란 러그', kind: 'FLOOR', cells: [2, 2], solid: false },
  'room/decor-rug-square.svg': { name: '네모 러그', kind: 'FLOOR', cells: [3, 2], solid: false },
  'room/decor-rug-star.svg': { name: '별 러그', kind: 'FLOOR', cells: [2, 2], solid: false },
  // 벽에 거는 것
  'room/decor-lights.svg': { name: '줄 조명', kind: 'WALL', cells: [3, 1], solid: false, drape: true },
  'room/decor-garland.svg': { name: '깃발 가랜드', kind: 'WALL', cells: [3, 1], solid: false, drape: true },
  'room/decor-clock.svg': { name: '벽시계', kind: 'WALL', cells: [1, 1], solid: false },
  'room/decor-picture.svg': { name: '작은 그림', kind: 'WALL', cells: [1, 1], solid: false },
  'room/decor-shelf.svg': { name: '벽 선반', kind: 'WALL', cells: [2, 1], solid: false },
}
export const decorOf = (assetKey: string | null | undefined): Decor | undefined => DECORS[assetKey ?? '']
/** 놓는 곳·크기 한 줄(예: "바닥 · 1칸", "벽 · 2×1칸") */
export const decorPlaceText = (assetKey: string | null | undefined) => {
  const d = decorOf(assetKey)
  if (!d) return '방 소품'
  const [w, h] = d.cells
  return `${d.kind === 'WALL' ? '벽' : '바닥'} · ${w * h === 1 ? '1칸' : `${w}×${h}칸`}`
}
/** 바닥 칸 이름(착용 없음은 벽지 세트 바닥) */
export const floorName = (assetKey: string | null | undefined) => floorOf(assetKey)?.name ?? '벽지와 같은 바닥'

// ---------- 착용 위치 기준점 (#557 표, #455 렌더링에서 사용, #648 친구 12종) ----------
type WearAnchor = { x: number; y: number; scale: number }
type WearAnchors = Record<'HAT' | 'OUTFIT' | 'ACCESSORY', WearAnchor>
/**
 * 설계 캔버스 `Mungchi.dc.html`의 모자 기준점 표(HAT) [x 이동, y 이동, 크기] 그대로. 친구마다 머리 꼭대기 위치와 폭이 다르다.
 */
const CANVAS_HAT: Record<FriendId, [number, number, number]> = {
  cotton: [0, 8, 1], cloud: [0, 2, 1.08], snow: [0, 10, 1], yarn: [0, 8, 1], moss: [0, 10, 1], sand: [0, 12, 0.86],
  star: [0, 0, 0.9], foam: [0, 10, 1], paper: [0, 8, 1], petal: [0, 6, 1.05], cone: [0, 2, 0.9], ice: [0, 12, 1],
}
const round = (n: number) => Math.round(n * 10) / 10
/**
 * 캔버스 모자 그림은 (100, 40)을 가운데로 가로 약 110(정사각형 120칸) 안에 그리고, (100, 60)을 기준으로 크기를 바꾼 뒤 옮긴다.
 * 같은 모자를 가로 60 그림 파일로 만들면 가운데 = (100 + x, 60 - 20 × 크기 + y), 배율 = 2 × 크기에서 캔버스와 같은 자리·크기가 된다.
 * 옷: 캔버스처럼 몸 폭 전체 띠(가로 -4~204, 위 160 언저리)를 그리고 `Companion`이 친구 몸 윤곽으로 잘라 친구마다 몸에 맞게 입힌다
 * (2026-11-16 사용자 의견 "옆으로 삐져나온대, 캐릭터마다 잘 맞게"). 그림 파일은 viewBox `-4 96 208 208`(가운데 (100, 200), 가로 208, 위 146 언저리 — 사용자 의견 2026-11-16 "옷을 조금만 더 올렸으면").
 * 소품: 친구 몸 앞쪽 끝(frontEdge)에 붙여 든 것처럼(예전에는 모든 친구가 x 174 한 자리라 좁은 친구는 떠 보였음). 파일은 가로 60, 가운데가 쥐는 곳.
 */
const OUTFIT_SIZE = 208
const anchorsFromCanvas = (id: FriendId, [x, y, s]: [number, number, number]): WearAnchors => ({
  HAT: { x: 100 + x, y: round(60 - 20 * s + y), scale: round(2 * s) },
  OUTFIT: { x: 100, y: 200, scale: OUTFIT_SIZE / 60 },
  ACCESSORY: { x: frontEdge(id) - 2, y: 152, scale: 1 },
})
/**
 * 친구 12종 × 모자·옷·소품 기준점. 친구 그림(`friendArt.ts`, viewBox 200×220 좌표)의 좌표이며 `scale`은 아이템 그림
 * 기본 크기(가로 60) 대비 배율. `Companion`의 `worn`이 이 표로 착용 그림을 겹쳐 그린다.
 */
export const FRIEND_WEAR_ANCHORS = Object.fromEntries(
  FRIENDS.map((f) => [f.id, anchorsFromCanvas(f.id, CANVAS_HAT[f.id])]),
) as Record<FriendId, WearAnchors>
/** 서버 값(캐릭터 12종, #697) 기준 기준점: 대응하는 친구의 값(예전 5종은 솜뭉치·솔방울뭉치·모래뭉치·이끼뭉치·구름뭉치, 새 7종은 같은 이름 친구) */
export const WEAR_ANCHORS = Object.fromEntries(
  COMPANIONS.map((c) => [c.id, FRIEND_WEAR_ANCHORS[companionToFriend(c.id)]]),
) as Record<CompanionId, WearAnchors>

// ---------- 착용 아이템 그림 파일 (#455·#557) ----------
/**
 * 착용 그림은 `frontend/web/public/student-assets/{assetKey}` 파일을 그대로 쓴다.
 * 관리자 아이템 "그림 키"(`look_item.asset_key`) = 이 폴더 안 경로(예 `looks/hat-acorn.svg`).
 * 파일이 아직 없으면 그 칸만 그리지 않아(기본 모습) 그림을 넣기만 하면 보인다.
 * 그림은 가로 60 기준 정사각형 안에 그리고, 기준점(FRIEND_WEAR_ANCHORS)이 그림 한가운데에 온다.
 */
export const WEAR_ASSET_BASE = '/student-assets/'
export const WEAR_ITEM_SIZE = 60
/** 그리는 순서(뒤에 그린 것이 위): 옷 → 모자 → 소품 */
export const WEAR_SLOTS = ['OUTFIT', 'HAT', 'ACCESSORY'] as const
export type WearSlot = (typeof WEAR_SLOTS)[number]
const SAFE_KEY = /^(?:[a-z0-9][a-z0-9_-]*\/)*[a-z0-9][a-z0-9_-]*\.(?:svg|png|webp)$/
/** 그림 키 → 파일 주소. 폴더 밖으로 나가거나 형식이 다르면 null(그리지 않음) */
export const wearAssetUrl = (assetKey: string | null | undefined) =>
  assetKey && SAFE_KEY.test(assetKey) ? WEAR_ASSET_BASE + assetKey : null
