import type { CompanionId } from '../../../domain/studentLook.ts'
import type { FurnitureSlot } from '../../../domain/retention.ts'

/**
 * 내 방 그림 리소스 표(#557, P27). 그림은 RoomArt.tsx, 이 파일은 assetKey·가격·위치 상수.
 * 관리자가 아이템을 등록할 때 아래 assetKey를 `look_item.asset_key`로 그대로 넣는다
 * (docs/report/retention-expansion.md 3.7).
 */
export const DEFAULT_WALLPAPER = 'room/wall-default.svg'

type Skin = { assetKey: string; name: string; main: string; trim: string; accent: string }
export const FURNITURE_SKINS: Record<FurnitureSlot, Skin[]> = {
  DESK: [
    { assetKey: 'room/desk-wood.svg', name: '나무 책상', main: '#C98F5A', trim: '#9C6A3E', accent: '#F2C14E' },
    { assetKey: 'room/desk-mint.svg', name: '민트 책상', main: '#9ED3C4', trim: '#5E9E8E', accent: '#F4ECDC' },
    { assetKey: 'room/desk-night.svg', name: '밤하늘 책상', main: '#3B4A78', trim: '#26305A', accent: '#FFF3C4' },
  ],
  WALL: [
    { assetKey: 'room/wall-cork.svg', name: '코르크 벽', main: '#D8B27E', trim: '#A9814F', accent: '#E3533C' },
    { assetKey: 'room/wall-wood.svg', name: '나무 벽', main: '#B98757', trim: '#7E5733', accent: '#F2C14E' },
    { assetKey: 'room/wall-pastel.svg', name: '구름 벽', main: '#DCE7F2', trim: '#9DB4CC', accent: '#F2B8A0' },
  ],
  WARDROBE: [
    { assetKey: 'room/wardrobe-wood.svg', name: '나무 옷장', main: '#B07A4C', trim: '#7E5733', accent: '#F2C14E' },
    { assetKey: 'room/wardrobe-sky.svg', name: '하늘 옷장', main: '#A8CBE8', trim: '#6F97BC', accent: '#FFFDF7' },
    { assetKey: 'room/wardrobe-berry.svg', name: '딸기 옷장', main: '#E58F95', trim: '#B55C64', accent: '#FFF3C4' },
  ],
}
/** 추가 스킨 해금값 기준안: 주간 최대 적립(약 125포인트)의 절반·한 주치 */
export const FURNITURE_SKIN_PRICES = [0, 60, 120]
export const skinOf = (slot: FurnitureSlot, assetKey: string | null) =>
  FURNITURE_SKINS[slot].find((s) => s.assetKey === assetKey) ?? FURNITURE_SKINS[slot][0]
export const furnitureSkinName = (slot: FurnitureSlot, assetKey: string | null) => skinOf(slot, assetKey).name

/** 추억의 벽 액자 슬롯 6개 위치(벽 그림 안 좌표, 2줄 × 3칸) */
export const FRAME_POSITIONS: { slotNo: number; x: number; y: number }[] = [1, 2, 3, 4, 5, 6].map((n) => ({
  slotNo: n,
  x: 18 + ((n - 1) % 3) * 76,
  y: 22 + Math.floor((n - 1) / 3) * 78,
}))
export const FRAME_SIZE = { w: 64, h: 64 }

// ---------- 착용 위치 기준점 (#557 표, #455 렌더링에서 사용) ----------
/**
 * 캐릭터 5종 × 모자·옷·소품 기준점. 각 캐릭터 SVG(`Companion.tsx`)의 viewBox 좌표이며 `scale`은 아이템 그림
 * 기본 크기(가로 60) 대비 배율. 착용 아이템 겹쳐 그리기는 #455에서 이 표를 쓴다(내 방은 #455 전 기본 모습).
 */
export const WEAR_ANCHORS: Record<CompanionId, Record<'HAT' | 'OUTFIT' | 'ACCESSORY', { x: number; y: number; scale: number }>> = {
  mungchi: { HAT: { x: 86, y: 26, scale: 0.6 }, OUTFIT: { x: 80, y: 88, scale: 0.7 }, ACCESSORY: { x: 112, y: 80, scale: 0.4 } },
  tori: { HAT: { x: 100, y: 58, scale: 1 }, OUTFIT: { x: 100, y: 158, scale: 1.05 }, ACCESSORY: { x: 150, y: 138, scale: 0.6 } },
  mongdol: { HAT: { x: 104, y: 78, scale: 1 }, OUTFIT: { x: 100, y: 152, scale: 1.1 }, ACCESSORY: { x: 160, y: 128, scale: 0.6 } },
  kongi: { HAT: { x: 104, y: 66, scale: 0.9 }, OUTFIT: { x: 106, y: 152, scale: 1 }, ACCESSORY: { x: 154, y: 120, scale: 0.6 } },
  monggeul: { HAT: { x: 118, y: 72, scale: 1 }, OUTFIT: { x: 104, y: 152, scale: 1.1 }, ACCESSORY: { x: 174, y: 130, scale: 0.6 } },
}
