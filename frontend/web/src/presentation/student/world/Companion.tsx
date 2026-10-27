import type { CSSProperties } from 'react'
import type { CompanionId } from '../../../domain/studentLook.ts'
import { companionLabel } from '../../../domain/studentLook.ts'

const INK = '#1F2421',
  CHEEK = '#F2B8A0'

/** 동행 캐릭터 5종 (테마 캔버스 Character 부품). decorative면 보조기기에서 숨긴다. */
export function Companion({
  kind,
  size = 120,
  decorative = false,
}: {
  kind: CompanionId
  size?: number
  decorative?: boolean
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
    style: { '--c': `${size}px` } as CSSProperties,
    ...a11y,
  }
  switch (kind) {
    case 'tori':
      return (
        <svg {...common} viewBox="30 30 140 156">
          <ellipse cx="100" cy="124" rx="52" ry="56" fill="#E6BD8F" stroke={INK} strokeWidth="4" />
          <rect x="94" y="38" width="12" height="22" rx="6" fill="#86593A" stroke={INK} strokeWidth="4" />
          <path d="M42 98 C40 58 160 58 158 98 C138 108 62 108 42 98Z" fill="#A8774F" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          <path d="M62 84 L74 72 M86 90 L100 70 M112 90 L126 72" stroke="#D6B08D" strokeWidth="3" strokeLinecap="round" />
          {face(132)}
        </svg>
      )
    case 'mongdol':
      return (
        <svg {...common} viewBox="26 60 150 120">
          <path d="M36 128 C34 96 64 74 104 74 C146 74 170 98 166 130 C162 158 132 170 100 170 C64 170 38 158 36 128Z" fill="#B8C2CC" stroke={INK} strokeWidth="4" />
          <circle cx="140" cy="100" r="3.5" fill="#E4E9EE" />
          <circle cx="62" cy="148" r="3" fill="#E4E9EE" />
          {face(120)}
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
        </svg>
      )
    case 'monggeul':
      return (
        <svg {...common} viewBox="14 52 178 128">
          <path d="M48 150 C24 150 22 116 46 110 C42 82 74 70 92 86 C102 60 144 62 148 92 C176 90 184 128 160 140 C164 156 146 164 132 158 C118 172 86 172 74 158 C64 164 52 160 48 150Z" fill="#DCE7F2" stroke={INK} strokeWidth="4" strokeLinejoin="round" />
          {face(118, 88, 120, 74, 134)}
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
        </svg>
      )
  }
}
