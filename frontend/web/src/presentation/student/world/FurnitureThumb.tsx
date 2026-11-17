import { floorPaint, skinOf, wallpaperOf } from './roomAssets.ts'
import { decorBg } from './decorDraw.ts'
import type { RoomSlot } from './roomAssets.ts'

const LINE = '#1F4E6B'

/**
 * 꾸미기·방 꾸미기 칸 그림(사용자 의견 2026-11-16 "가독성이 없어, 뭐가 어떻게 변하는지 보여야지"): 색 네모 대신
 * 그 칸이 바꾸는 가구를 그 색으로 작게 그린다. 세트(roomAssets ROOM_SET_PARTS)까지 함께 그려 같이 바뀌는 것이 보이게 한다.
 * 벽지: 벽 조각 + 기본 바닥 + 커튼 / 바닥: 넓은 바닥(벽은 흐리게) / 책상: 책상 + 책장 / 추억의 벽: 게시판 + 액자 테두리 / 옷장: 옷장 + 문.
 */
export function FurnitureThumb({ slot, assetKey, wallpaper }: { slot: RoomSlot; assetKey: string | null | undefined; wallpaper?: string | null }) {
  if (slot === 'FLOOR') {
    // 바닥 칸: 바닥이 칸 대부분을 차지하게(무엇이 바뀌는지 보이게). 착용 없음 칸은 지금 벽지 세트의 바닥
    return (
      <span className="st-fthumb st-fthumb-wall st-fthumb-floorpick" aria-hidden="true">
        <span className="st-fthumb-paper" style={{ background: wallpaperOf(wallpaper).paint, opacity: 0.55 }} />
        <span className="st-fthumb-floor" style={{ background: floorPaint(assetKey, wallpaper, true) }} />
      </span>
    )
  }
  if (slot === 'BACKGROUND') {
    const wp = wallpaperOf(assetKey)
    return (
      <span className="st-fthumb st-fthumb-wall" aria-hidden="true">
        <span className="st-fthumb-paper" style={{ background: wp.paint }} />
        <span className="st-fthumb-window" />
        <span className="st-fthumb-curtain is-left" style={{ background: wp.curtain }} />
        <span className="st-fthumb-curtain is-right" style={{ background: wp.curtain }} />
        <span className="st-fthumb-floor" style={{ background: `repeating-linear-gradient(90deg, ${wp.floor[0]} 0 10px, ${wp.floor[1]} 10px 11px)` }} />
      </span>
    )
  }
  const skin = skinOf(slot, assetKey)
  const [top, front, side] = skin.faces
  const set = skin.set
  return (
    <span className="st-fthumb" aria-hidden="true">
      <svg viewBox="0 0 100 80" width="100%" height="100%">
        <rect x="0" y="66" width="100" height="14" fill="#E9D2A8" />
        {slot === 'DESK' && (
          <g stroke={LINE} strokeWidth="2" strokeLinejoin="round">
            {/* 책장(세트) */}
            <rect x="6" y="10" width="34" height="58" rx="2" fill={set[1]} />
            {[24, 38, 52].map((y) => <rect key={y} x="6" y={y} width="34" height="3" fill={set[2]} strokeWidth="1" />)}
            <g strokeWidth="1">
              <rect x="10" y="14" width="5" height="10" fill="#E3533C" /><rect x="16" y="15" width="5" height="9" fill="#FFD84D" /><rect x="25" y="14" width="5" height="10" fill="#7FC8D8" />
              <rect x="11" y="28" width="5" height="10" fill="#9CCB8C" /><rect x="18" y="29" width="5" height="9" fill="#F7AEC4" />
              <rect x="12" y="42" width="5" height="10" fill="#FFD84D" /><rect x="27" y="43" width="5" height="9" fill="#E3533C" />
            </g>
            {/* 책상 */}
            <rect x="44" y="40" width="52" height="7" rx="1.5" fill={top} />
            <rect x="46" y="47" width="48" height="5" fill={front} />
            <rect x="49" y="52" width="5" height="16" fill={side} />
            <rect x="86" y="52" width="5" height="16" fill={side} />
            <rect x="56" y="33" width="16" height="7" fill="#FFD84D" strokeWidth="1.5" />
          </g>
        )}
        {slot === 'WARDROBE' && (
          <g stroke={LINE} strokeWidth="2" strokeLinejoin="round">
            {/* 옷장 */}
            <rect x="6" y="6" width="50" height="62" rx="2" fill={front} />
            <rect x="6" y="6" width="50" height="6" fill={top} />
            <line x1="31" y1="12" x2="31" y2="68" />
            <circle cx="27" cy="40" r="2" fill="#3A2A20" stroke="none" />
            <circle cx="35" cy="40" r="2" fill="#3A2A20" stroke="none" />
            {/* 문(세트): 문틀 + 문판 + 손잡이 */}
            <rect x="62" y="14" width="34" height="54" rx="3" fill={set[0]} />
            <rect x="67" y="19" width="24" height="49" rx="2" fill={set[1]} />
            <circle cx="86" cy="45" r="2.4" fill={set[2]} stroke="none" />
          </g>
        )}
        {slot === 'WALL' && (
          <g stroke={LINE} strokeLinejoin="round">
            {/* 추억의 벽 게시판 + 액자 두 장(세트: 액자 테두리) */}
            <rect x="6" y="8" width="88" height="56" rx="6" fill={top} strokeWidth="2.5" />
            <rect x="11" y="13" width="78" height="46" rx="3" fill="none" stroke={front} strokeWidth="2" />
            <rect x="18" y="19" width="28" height="22" fill="#CFE6FA" stroke={set[0]} strokeWidth="5" />
            <rect x="54" y="30" width="28" height="22" fill="#FFE9A8" stroke={set[0]} strokeWidth="5" />
          </g>
        )}
      </svg>
    </span>
  )
}

/** 방 소품 칸 그림(#705): 방 안 그림과 같은 그림(decorDraw.ts), 고른 색으로. 그림 목록에 없는 키는 물음표 상자 */
export function DecorThumb({ assetKey, color }: { assetKey: string | null | undefined; color?: string | null }) {
  const bg = decorBg(assetKey, color)
  return (
    <span className="st-fthumb st-dthumb" aria-hidden="true" style={{ background: bg === 'none' ? undefined : `${bg}, #FFFDF6` }}>
      {bg === 'none' && <svg viewBox="0 0 100 80" width="100%" height="100%"><rect x="30" y="22" width="40" height="36" rx="4" fill="#F1E6D2" stroke={LINE} strokeWidth="2" /><text x="50" y="47" textAnchor="middle" fontSize="18" fill={LINE}>?</text></svg>}
    </span>
  )
}
