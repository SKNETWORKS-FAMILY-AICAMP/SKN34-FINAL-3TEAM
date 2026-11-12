import type { ReactNode } from 'react'
import { DEFAULT_WALLPAPER, FRAME_SIZE, skinOf } from './roomAssets.ts'

/**
 * 내 방 그림 리소스(#557, P27). 기존 화면처럼 인라인 SVG로 그리고 `look_item.asset_key`와 1:1로 찾는다.
 * 관리자가 아이템을 등록할 때 아래 표의 assetKey를 그대로 넣으면 된다(docs/report/retention-expansion.md 3.7).
 * 모르는 assetKey는 기본 그림으로 그려 화면이 깨지지 않게 한다.
 *
 * 좌표계: 방 전체 viewBox 0 0 800 480. 바닥선 y=360.
 */
const INK = '#1F2421'

// ---------- 벽지 (BACKGROUND 착용 아이템 = 방 벽지, 없으면 기본) ----------
type Paint = { base: string; pattern: ReactNode }
const dots = (fill: string) => (
  <g fill={fill} opacity="0.55">
    {Array.from({ length: 40 }, (_, i) => <circle key={i} cx={20 + (i % 10) * 80 + ((i / 10) | 0) % 2 * 40} cy={30 + ((i / 10) | 0) * 80} r="5" />)}
  </g>
)
const WALLPAPERS: Record<string, Paint> = {
  'room/wall-default.svg': { base: '#F6EEDD', pattern: dots('#E6D7B8') },
  // 기존 배경 아이템(별빛 배경)을 방 벽지로 그대로 씀: 같은 assetKey, 방 비율에 맞춘 그림
  'looks/bg-stars.svg': {
    base: '#26305A',
    pattern: (
      <g fill="#FFF3C4">
        {[[60, 50], [180, 110], [300, 40], [420, 130], [540, 60], [660, 120], [740, 40], [120, 200], [360, 220], [600, 210], [700, 260], [240, 270]].map(([x, y], i) => (
          <path key={i} d={`M${x} ${y - 9} L${x + 3} ${y - 3} L${x + 9} ${y} L${x + 3} ${y + 3} L${x} ${y + 9} L${x - 3} ${y + 3} L${x - 9} ${y} L${x - 3} ${y - 3}Z`} />
        ))}
      </g>
    ),
  },
}
export function Wallpaper({ assetKey }: { assetKey: string | null }) {
  const paint = WALLPAPERS[assetKey ?? ''] ?? WALLPAPERS[DEFAULT_WALLPAPER]
  return (
    <g>
      <rect x="0" y="0" width="800" height="360" fill={paint.base} />
      {paint.pattern}
      <rect x="0" y="360" width="800" height="120" fill="#D9B98C" />
      <path d="M0 360 H800" stroke={INK} strokeWidth="4" />
      {[120, 280, 440, 600].map((x) => <path key={x} d={`M${x} 368 L${x - 40} 480`} stroke="#C4A274" strokeWidth="3" />)}
    </g>
  )
}

// ---------- 가구 스킨 (DESK·WALL·WARDROBE, 기본 1 + 추가 2, 기준안) ----------

export function Desk({ assetKey }: { assetKey: string | null }) {
  const s = skinOf('DESK', assetKey)
  return (
    <g>
      <rect x="0" y="0" width="200" height="22" rx="6" fill={s.main} stroke={INK} strokeWidth="4" />
      <rect x="14" y="22" width="20" height="96" fill={s.trim} stroke={INK} strokeWidth="4" />
      <rect x="166" y="22" width="20" height="96" fill={s.trim} stroke={INK} strokeWidth="4" />
      <rect x="110" y="26" width="56" height="40" rx="4" fill={s.main} stroke={INK} strokeWidth="4" />
      <circle cx="138" cy="46" r="5" fill={s.accent} stroke={INK} strokeWidth="3" />
      {/* 책 두 권과 연필꽂이 */}
      <rect x="26" y="-34" width="18" height="34" fill="#E3533C" stroke={INK} strokeWidth="3" />
      <rect x="46" y="-28" width="16" height="28" fill="#4F8FC0" stroke={INK} strokeWidth="3" />
      <rect x="150" y="-26" width="24" height="26" rx="4" fill={s.accent} stroke={INK} strokeWidth="3" />
      <path d="M156 -26 L154 -44 M164 -26 L168 -42" stroke={INK} strokeWidth="3" strokeLinecap="round" />
    </g>
  )
}

export function MemoryWall({ assetKey, children }: { assetKey: string | null; children?: ReactNode }) {
  const s = skinOf('WALL', assetKey)
  return (
    <g>
      <rect x="0" y="0" width="246" height="190" rx="10" fill={s.main} stroke={INK} strokeWidth="4" />
      <rect x="8" y="8" width="230" height="174" rx="6" fill="none" stroke={s.trim} strokeWidth="3" strokeDasharray="6 6" />
      <circle cx="123" cy="10" r="6" fill={s.accent} stroke={INK} strokeWidth="3" />
      {children}
    </g>
  )
}
/** 액자 테두리. 빈 슬롯은 점선 */
export function FrameBorder({ filled, children }: { filled: boolean; children?: ReactNode }) {
  return filled ? (
    <g>
      <rect x="0" y="0" width={FRAME_SIZE.w} height={FRAME_SIZE.h} rx="4" fill="#FFFDF7" stroke={INK} strokeWidth="4" />
      <rect x="6" y="6" width={FRAME_SIZE.w - 12} height={FRAME_SIZE.h - 12} rx="2" fill="#F4ECDC" stroke="#C4A274" strokeWidth="2" />
      {children}
    </g>
  ) : (
    <rect x="0" y="0" width={FRAME_SIZE.w} height={FRAME_SIZE.h} rx="4" fill="rgba(255,253,247,0.45)" stroke={INK} strokeWidth="2.5" strokeDasharray="6 5" />
  )
}

export function Wardrobe({ assetKey }: { assetKey: string | null }) {
  const s = skinOf('WARDROBE', assetKey)
  return (
    <g>
      <rect x="0" y="0" width="150" height="230" rx="10" fill={s.main} stroke={INK} strokeWidth="4" />
      <path d="M75 12 V220" stroke={INK} strokeWidth="4" />
      <rect x="12" y="12" width="51" height="208" rx="6" fill="none" stroke={s.trim} strokeWidth="3" />
      <rect x="87" y="12" width="51" height="208" rx="6" fill="none" stroke={s.trim} strokeWidth="3" />
      <circle cx="64" cy="116" r="6" fill={s.accent} stroke={INK} strokeWidth="3" />
      <circle cx="86" cy="116" r="6" fill={s.accent} stroke={INK} strokeWidth="3" />
      <rect x="10" y="230" width="20" height="12" fill={s.trim} stroke={INK} strokeWidth="3" />
      <rect x="120" y="230" width="20" height="12" fill={s.trim} stroke={INK} strokeWidth="3" />
    </g>
  )
}

