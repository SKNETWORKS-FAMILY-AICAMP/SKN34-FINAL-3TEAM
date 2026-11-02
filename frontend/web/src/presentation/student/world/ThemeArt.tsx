import type { Theme, ThemeId } from '../../../domain/studentLook.ts'

const INK = '#1F2421'

/** 테마별 바탕 무늬 (테마 캔버스 배경). 장식이므로 보조기기에서 숨긴다. */
export function ThemeBackdrop({ t }: { t: Theme }) {
  return (
    <svg
      className="st-backdrop"
      aria-hidden="true"
      viewBox="0 0 1194 834"
      preserveAspectRatio="xMidYMid slice"
    >
      {t.id === 'lake' && (
        <g>
          <path d="M60 520 C260 470 480 560 760 480 C960 420 1090 470 1194 430" stroke={t.shade} strokeWidth="120" fill="none" />
          <path d="M0 160 C200 120 360 220 560 150" stroke={t.shade} strokeWidth="70" fill="none" />
          <path d="M640 0 H1194 V250 C1120 220 1060 170 980 150 C880 125 760 90 640 0 Z" fill={t.light} opacity="0.35" />
          <path d="M1194 834 H760 C840 790 930 770 1010 730 C1090 690 1140 700 1194 660 Z" fill={t.light} opacity="0.35" />
          <g fill="#24585C">
            <path d="M330 690 q14 -8 28 0 q-14 8 -28 0 Z" />
            <path d="M380 712 q10 -6 20 0 q-10 6 -20 0 Z" />
            <path d="M1000 410 q14 -8 28 0 q-14 8 -28 0 Z" />
          </g>
        </g>
      )}
      {t.id === 'forest' && (
        <g>
          <path d="M0 560 C220 500 420 600 700 520 C900 460 1060 520 1194 470" stroke={t.shade} strokeWidth="110" fill="none" />
          <g fill={t.shade}>
            <path d="M40 120 L70 40 L100 120 Z" />
            <path d="M90 140 L124 50 L158 140 Z" />
            <path d="M390 80 L414 20 L438 80 Z" />
            <path d="M1040 400 L1072 320 L1104 400 Z" />
            <path d="M1100 420 L1130 350 L1160 420 Z" />
            <path d="M300 760 L330 690 L360 760 Z" />
          </g>
          <g fill={t.light} opacity="0.4">
            <path d="M760 70 L786 10 L812 70 Z" />
            <path d="M840 90 L870 20 L900 90 Z" />
            <path d="M1060 80 L1094 0 L1128 80 Z" />
            <path d="M1060 800 L1092 720 L1124 800 Z" />
          </g>
        </g>
      )}
      {t.id === 'factory' && (
        <g>
          <g stroke={t.shade} strokeWidth="2">
            {[140, 300, 460, 620, 780].map((y) => (
              <path key={y} d={`M0 ${y} H1194`} />
            ))}
            {[160, 400, 640, 880, 1120].map((x) => (
              <path key={x} d={`M${x} 0 V834`} />
            ))}
          </g>
          <rect x="0" y="520" width="1194" height="54" fill={t.shade} />
          <g fill={t.light} opacity="0.5">
            {[40, 140, 840, 940, 1040, 1140].map((x) => (
              <circle key={x} cx={x} cy="547" r="14" />
            ))}
          </g>
          <g fill="none" stroke={t.light2} strokeWidth="14" opacity="0.4">
            <circle cx="1110" cy="740" r="54" />
            <circle cx="1010" cy="790" r="34" />
          </g>
        </g>
      )}
      {t.id === 'space' && (
        <g>
          <circle cx="1120" cy="40" r="170" fill={t.shade} />
          <ellipse cx="1120" cy="40" rx="250" ry="56" fill="none" stroke={t.light} strokeWidth="5" opacity="0.6" transform="rotate(-14 1120 40)" />
          <circle cx="60" cy="800" r="120" fill={t.shade} />
          <g fill={t.light2}>
            {[
              [60, 60, 3], [240, 110, 2], [420, 40, 3], [610, 90, 2], [860, 200, 3], [1000, 330, 2],
              [1150, 420, 3], [420, 380, 2], [560, 560, 3], [1150, 620, 2], [860, 790, 3], [300, 250, 2],
            ].map(([x, y, r]) => (
              <circle key={`${x}-${y}`} cx={x} cy={y} r={r} />
            ))}
          </g>
        </g>
      )}
      {t.id === 'sea' && (
        <g>
          <g fill={t.light} opacity="0.12">
            <path d="M120 0 H260 L420 834 H300 Z" />
            <path d="M560 0 H640 L760 834 H680 Z" />
            <path d="M900 0 H1020 L1150 834 H1060 Z" />
          </g>
          <path d="M0 700 C200 660 380 740 620 690 C860 640 1040 700 1194 660 V834 H0 Z" fill={t.shade} />
          <g fill="none" stroke={t.light2} strokeWidth="3" opacity="0.6">
            <circle cx="1080" cy="300" r="10" />
            <circle cx="1100" cy="250" r="6" />
            <circle cx="400" cy="90" r="8" />
          </g>
        </g>
      )}
    </svg>
  )
}

/** 생각 유형 한 곳(섬·공터·작업대…). 깃발 색은 유형별, 땅 색과 장식은 테마별. */
export function IslandArt({ t, hue, today }: { t: Theme; hue: string; today: boolean }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 200 120" className="st-island-art">
      {today && (
        <ellipse cx="100" cy="64" rx="96" ry="54" fill="none" stroke="#F2A65A" strokeWidth="3" strokeDasharray="6 8" />
      )}
      <path d="M18 74 C10 46 52 26 98 28 C146 22 192 40 186 74 C190 104 140 116 100 112 C54 116 22 104 18 74 Z" fill={t.side} />
      <path d="M18 64 C10 36 52 16 98 18 C146 12 192 30 186 64 C190 94 140 106 100 102 C54 106 22 94 18 64 Z" fill={t.top} />
      <IslandDecor id={t.id} />
      <path d="M100 66 V20" stroke={INK} strokeWidth="2.5" />
      <path d="M100 20 L128 28 L100 36 Z" fill={hue} />
    </svg>
  )
}
function IslandDecor({ id }: { id: ThemeId }) {
  if (id === 'forest')
    return (
      <g>
        <path d="M36 70 L50 38 L64 70 Z" fill="#4F7A3A" />
        <path d="M140 72 L154 42 L168 72 Z" fill="#6E9A4A" />
      </g>
    )
  if (id === 'factory')
    return (
      <g fill="none" stroke="#6E6A62" strokeWidth="5">
        <circle cx="50" cy="60" r="11" />
        <rect x="138" y="48" width="26" height="22" rx="3" />
      </g>
    )
  if (id === 'space')
    return (
      <g fill="#B8AE9C">
        <ellipse cx="50" cy="62" rx="14" ry="7" />
        <ellipse cx="150" cy="66" rx="10" ry="5" />
        <ellipse cx="128" cy="48" rx="6" ry="3" />
      </g>
    )
  if (id === 'sea')
    return (
      <g fill="none" stroke="#E07A5F" strokeWidth="5" strokeLinecap="round">
        <path d="M48 72 V50 M48 60 L38 48 M48 56 L58 46" />
        <path d="M152 72 V54 M152 62 L162 52" />
      </g>
    )
  return (
    <g stroke="#6E8F3A" strokeWidth="2.5" strokeLinecap="round">
      <path d="M50 70 l-3 -10" />
      <path d="M55 70 l2 -12" />
      <path d="M150 74 l-2 -10" />
      <path d="M156 74 l3 -9" />
    </g>
  )
}

/** 캐릭터가 타고 다니는 탈것 (테마별). */
export function Ride({ id }: { id: ThemeId }) {
  return (
    <svg aria-hidden="true" viewBox="-12 0 192 70" className="st-ride">
      {id === 'lake' && (
        <g>
          <path d="M14 16 H166 L148 46 Q90 56 32 46 Z" fill="#E9B949" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
          <path d="M8 62 q16 -8 32 0 q16 8 32 0 q16 -8 32 0 q16 8 32 0 q16 -8 32 0" stroke="#C6EAE1" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        </g>
      )}
      {id === 'forest' && (
        <g>
          <rect x="20" y="12" width="140" height="30" rx="4" fill="#B07A45" stroke={INK} strokeWidth="2.5" />
          <circle cx="50" cy="50" r="13" fill="#5A4030" stroke={INK} strokeWidth="2.5" />
          <circle cx="130" cy="50" r="13" fill="#5A4030" stroke={INK} strokeWidth="2.5" />
        </g>
      )}
      {id === 'factory' && (
        <g>
          <rect x="18" y="10" width="144" height="32" rx="6" fill="#E9B949" stroke={INK} strokeWidth="2.5" />
          <circle cx="44" cy="52" r="10" fill="#6E6A62" stroke={INK} strokeWidth="2.5" />
          <circle cx="136" cy="52" r="10" fill="#6E6A62" stroke={INK} strokeWidth="2.5" />
          <path d="M0 64 H180" stroke="#F4D88A" strokeWidth="4" />
        </g>
      )}
      {id === 'space' && (
        <g>
          <path d="M30 20 H140 Q172 30 140 44 H30 Z" fill="#E4E0D8" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
          <circle cx="120" cy="32" r="6" fill="#7FB3D5" stroke={INK} strokeWidth="2" />
          <path d="M30 24 L10 14 L14 32 L10 50 L30 40 Z" fill="#E07A5F" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
          <path d="M6 32 H-10" stroke="#F2C14E" strokeWidth="6" strokeLinecap="round" />
        </g>
      )}
      {id === 'sea' && (
        <g>
          <ellipse cx="90" cy="32" rx="78" ry="22" fill="#E9B949" stroke={INK} strokeWidth="2.5" />
          <circle cx="56" cy="32" r="8" fill="#B5E3EC" stroke={INK} strokeWidth="2" />
          <circle cx="90" cy="32" r="8" fill="#B5E3EC" stroke={INK} strokeWidth="2" />
          <path d="M168 24 L180 16 V48 L168 40" fill="#E9B949" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
        </g>
      )}
    </svg>
  )
}

/** 테마 고르기 카드의 작은 미리보기 */
export function ThemeSwatch({ t }: { t: Theme }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 160 92" className="st-swatch">
      <rect width="160" height="92" rx="12" fill={t.bg} />
      <circle cx="128" cy="30" r="18" fill={t.light} />
      <ellipse cx="46" cy="70" rx="30" ry="12" fill={t.side} />
      <ellipse cx="46" cy="64" rx="30" ry="12" fill={t.top} />
    </svg>
  )
}
