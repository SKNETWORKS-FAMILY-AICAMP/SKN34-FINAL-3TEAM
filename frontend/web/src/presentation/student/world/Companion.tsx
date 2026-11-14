import { useState } from 'react'
import type { CSSProperties } from 'react'
import type { CompanionId } from '../../../domain/studentLook.ts'
import { companionLabel } from '../../../domain/studentLook.ts'
import { WEAR_ANCHORS, WEAR_ITEM_SIZE, WEAR_SLOTS, wearAssetUrl } from './roomAssets.ts'
import type { WearSlot } from './roomAssets.ts'

const INK = '#1F2421',
  CHEEK = '#F2B8A0'

/**
 * 착용 아이템 겹쳐 그리기(#455). 칸마다 `public/student-assets/{그림 키}` 파일을 캐릭터별 기준점(WEAR_ANCHORS)에
 * 그린다. 파일이 없거나 못 읽으면 그 칸만 빼고 기본 모습으로 둔다(그림을 넣기만 하면 보임).
 */
function Worn({ kind, worn }: { kind: CompanionId; worn: Partial<Record<WearSlot, string | null>> }) {
  const [broken, setBroken] = useState<string[]>([])
  return (
    <g className="st-worn">
      {WEAR_SLOTS.map((slot) => {
        const href = wearAssetUrl(worn[slot])
        if (!href || broken.includes(href)) return null
        const { x, y, scale } = WEAR_ANCHORS[kind][slot]
        const w = WEAR_ITEM_SIZE * scale
        return (
          <image key={slot} data-slot={slot} href={href} x={x - w / 2} y={y - w / 2} width={w} height={w}
            preserveAspectRatio="xMidYMid meet" onError={() => setBroken((list) => [...list, href])} />
        )
      })}
    </g>
  )
}

/** 동행 캐릭터 5종 (테마 캔버스 Character 부품). decorative면 보조기기에서 숨긴다. worn은 착용 칸 그림 키(#455). */
export function Companion({
  kind,
  size = 120,
  decorative = false,
  worn,
}: {
  kind: CompanionId
  size?: number
  decorative?: boolean
  worn?: Partial<Record<WearSlot, string | null>>
}) {
  const a11y = decorative
    ? ({ 'aria-hidden': true } as const)
    : ({ role: 'img', 'aria-label': companionLabel(kind) } as const)
  const face = (y: number, x1 = 84, x2 = 116, cx1 = 70, cx2 = 130) => (
    <>
      <circle cx={x1} cy={y} r="6" fill={INK} />
      <circle cx={x2} cy={y} r="6" fill={INK} />
      <path
        d={`M${(x1 + x2) / 2 - 8} ${y + 14} Q${(x1 + x2) / 2} ${y + 21} ${(x1 + x2) / 2 + 8} ${y + 14}`}
        stroke={INK}
        strokeWidth="3.5"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx={cx1} cy={y + 14} r="7" fill={CHEEK} />
      <circle cx={cx2} cy={y + 14} r="7" fill={CHEEK} />
    </>
  )
  const common = {
    width: size,
    height: size,
    className: 'st-companion',
    // 모자처럼 몸 밖으로 나가는 착용 그림이 잘리지 않게
    style: { '--c': `${size}px`, overflow: 'visible' } as CSSProperties,
    ...a11y,
  }
  const wear = worn && <Worn kind={kind} worn={worn} />
  switch (kind) {
    case 'tori':
      return (
        <svg {...common} viewBox="30 30 140 156">
          <ellipse cx="100" cy="124" rx="52" ry="56" fill="#E6BD8F" stroke={INK} strokeWidth="4" />
          <rect x="94" y="38" width="12" height="22" rx="6" fill="#86593A" stroke={INK} strokeWidth="4" />
          <path d="M42 98 C40 58 160 58 158 98 C138 108 62 108 42 98Z" fill="#A8774F" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          <path d="M62 84 L74 72 M86 90 L100 70 M112 90 L126 72" stroke="#D6B08D" strokeWidth="3" strokeLinecap="round" />
          {face(132)}
          {wear}
        </svg>
      )
    case 'mongdol':
      return (
        <svg {...common} viewBox="26 60 150 120">
          <path d="M36 128 C34 96 64 74 104 74 C146 74 170 98 166 130 C162 158 132 170 100 170 C64 170 38 158 36 128Z" fill="#B8C2CC" stroke={INK} strokeWidth="4" />
          <circle cx="140" cy="100" r="3.5" fill="#E4E9EE" />
          <circle cx="62" cy="148" r="3" fill="#E4E9EE" />
          {face(120)}
          {wear}
        </svg>
      )
    case 'kongi':
      return (
        <svg {...common} viewBox="40 12 132 166">
          <path d="M102 66 C102 52 103 42 102 30" fill="none" stroke={INK} strokeWidth="6" strokeLinecap="round" />
          <path d="M102 66 C102 52 103 42 102 30" fill="none" stroke="#6AA65A" strokeWidth="3" strokeLinecap="round" />
          <path d="M102 36 C86 20 62 22 56 36 C70 46 90 46 102 36Z" fill="#79B866" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          <path d="M102 36 C116 18 142 18 150 32 C136 44 114 46 102 36Z" fill="#8CC674" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          <path d="M56 102 C52 74 74 60 98 64 C112 66 120 74 134 70 C156 66 162 96 156 124 C150 156 124 172 98 170 C70 168 58 136 56 102Z" fill="#CFE2A3" stroke={INK} strokeWidth="4" />
          {face(114, 90, 122, 76, 136)}
          {wear}
        </svg>
      )
    case 'monggeul':
      return (
        <svg {...common} viewBox="14 52 178 128">
          <path d="M48 150 C24 150 22 116 46 110 C42 82 74 70 92 86 C102 60 144 62 148 92 C176 90 184 128 160 140 C164 156 146 164 132 158 C118 172 86 172 74 158 C64 164 52 160 48 150Z" fill="#DCE7F2" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          {face(118, 88, 120, 74, 134)}
          {wear}
        </svg>
      )
    default:
      return (
        <svg {...common} viewBox="34 20 92 90">
          <g fill={INK}>
            <circle cx="62" cy="62" r="24.5" />
            <circle cx="86" cy="52" r="28.5" />
            <circle cx="100" cy="74" r="20.5" />
            <circle cx="72" cy="80" r="22.5" />
          </g>
          <g fill="#FFFDF7">
            <circle cx="62" cy="62" r="22" />
            <circle cx="86" cy="52" r="26" />
            <circle cx="100" cy="74" r="18" />
            <circle cx="72" cy="80" r="20" />
          </g>
          <circle cx="76" cy="60" r="3.2" fill={INK} />
          <circle cx="92" cy="60" r="3.2" fill={INK} />
          <path d="M78 69 Q84 75 90 69" stroke={INK} strokeWidth="2.4" fill="none" strokeLinecap="round" />
          <circle cx="69" cy="68" r="3.4" fill={CHEEK} />
          <circle cx="98" cy="68" r="3.4" fill={CHEEK} />
          {wear}
        </svg>
      )
  }
}
