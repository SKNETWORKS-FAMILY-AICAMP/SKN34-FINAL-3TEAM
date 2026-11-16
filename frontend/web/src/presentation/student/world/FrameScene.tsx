/**
 * 기념 액자 기본 그림(회차 그림 주소가 없을 때). 예전에는 산 하나에 색만 달라 액자가 모두 같아 보였다
 * (사용자 의견 2026-11-16 "액자도 그림이 너무 일정해"). 장면 다섯 가지 중 제목 낱말에 맞는 것을 먼저 고르고,
 * 없으면 테마 ID로 고른다. 추억 앨범·회차 상세·내 방 추억의 벽이 같이 쓴다.
 */
type Scene = 'sea' | 'night' | 'forest' | 'village' | 'meadow'
const SCENES: Scene[] = ['sea', 'night', 'forest', 'village', 'meadow']
const WORDS: [RegExp, Scene][] = [
  [/바다|섬|지도|등대|항구|물|배/, 'sea'],
  [/별|밤|달|우주|우체국|하늘/, 'night'],
  [/숲|나무|발명|동물|도토리/, 'forest'],
  [/마을|시계|도서관|학교|가게|축제/, 'village'],
]
function sceneOf(themeId: string, title = ''): Scene {
  const hit = WORDS.find(([re]) => re.test(title))
  if (hit) return hit[1]
  return SCENES[[...themeId].reduce((n, c) => n + c.charCodeAt(0), 0) % SCENES.length]
}

const L = '#1F2421'

export function FrameScene({ themeId, title, className, muted = false }: { themeId: string; title?: string; className?: string; muted?: boolean }) {
  const scene = sceneOf(themeId, title)
  return (
    <svg className={className} viewBox="0 0 120 90" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false"
      data-scene={scene} style={muted ? { filter: 'grayscale(1) opacity(.45)' } : undefined}>
      {scene === 'sea' && (
        <>
          <rect width="120" height="90" fill="#BFE6F5" />
          <circle cx="96" cy="20" r="9" fill="#F2C14E" />
          <path d="M0 58 Q30 52 60 58 T120 58 V90 H0Z" fill="#5BAFC2" stroke={L} strokeWidth="2" />
          <path d="M28 60 Q46 40 64 60Z" fill="#E9D2A8" stroke={L} strokeWidth="2" />
          <rect x="43" y="34" width="6" height="22" fill="#FFFFFF" stroke={L} strokeWidth="2" />
          <path d="M42 34 L46 27 L50 34Z" fill="#E3533C" stroke={L} strokeWidth="1.5" />
          <path d="M80 70 L100 70 L96 76 L84 76Z M90 70 V60 L98 68Z" fill="#FFFFFF" stroke={L} strokeWidth="1.8" strokeLinejoin="round" />
        </>
      )}
      {scene === 'night' && (
        <>
          <rect width="120" height="90" fill="#2A2070" />
          <circle cx="92" cy="22" r="10" fill="#FFE45C" />
          <circle cx="97" cy="18" r="9" fill="#2A2070" />
          {[[18, 16], [40, 28], [62, 12], [30, 44], [76, 36], [108, 46]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.8" fill="#FFFFFF" />)}
          <path d="M0 72 Q60 58 120 72 V90 H0Z" fill="#4A42A0" stroke={L} strokeWidth="2" />
          <path d="M44 72 V56 L56 46 L68 56 V72Z" fill="#E9C79B" stroke={L} strokeWidth="2" strokeLinejoin="round" />
          <rect x="52" y="60" width="8" height="8" fill="#FFE45C" stroke={L} strokeWidth="1.5" />
        </>
      )}
      {scene === 'forest' && (
        <>
          <rect width="120" height="90" fill="#DDF6D2" />
          <circle cx="20" cy="18" r="8" fill="#F2C14E" />
          <path d="M0 74 H120 V90 H0Z" fill="#9CCB8C" stroke={L} strokeWidth="2" />
          {[[30, 1], [60, 1.2], [92, 0.95]].map(([x, s]) => (
            <g key={x} transform={`translate(${x} 74) scale(${s})`}>
              <rect x="-3" y="-14" width="6" height="14" fill="#8A5A33" stroke={L} strokeWidth="1.8" />
              <path d="M0 -46 L16 -14 H-16Z" fill="#5E9E4E" stroke={L} strokeWidth="2" strokeLinejoin="round" />
            </g>
          ))}
          <circle cx="76" cy="70" r="3" fill="#A8774F" stroke={L} strokeWidth="1.2" />
        </>
      )}
      {scene === 'village' && (
        <>
          <rect width="120" height="90" fill="#FFF1D6" />
          <circle cx="100" cy="18" r="8" fill="#F2C14E" />
          <path d="M0 76 H120 V90 H0Z" fill="#E9D2A8" stroke={L} strokeWidth="2" />
          <path d="M14 76 V54 L28 42 L42 54 V76Z" fill="#F7AEC4" stroke={L} strokeWidth="2" strokeLinejoin="round" />
          <path d="M50 76 V30 L60 20 L70 30 V76Z" fill="#B8D8EE" stroke={L} strokeWidth="2" strokeLinejoin="round" />
          <circle cx="60" cy="40" r="5" fill="#FFFFFF" stroke={L} strokeWidth="1.5" />
          <path d="M78 76 V56 L92 46 L106 56 V76Z" fill="#FFDF6B" stroke={L} strokeWidth="2" strokeLinejoin="round" />
        </>
      )}
      {scene === 'meadow' && (
        <>
          <rect width="120" height="90" fill="#C6EAE1" />
          <circle cx="90" cy="20" r="9" fill="#F2C14E" />
          <path d="M0 64 Q40 44 80 60 T120 56 V90 H0Z" fill="#9CCB8C" stroke={L} strokeWidth="2" />
          {[[24, 74, '#F7AEC4'], [44, 80, '#FFE45C'], [70, 76, '#FFFFFF'], [96, 80, '#F7AEC4']].map(([x, y, c]) => (
            <circle key={`${x}`} cx={x} cy={y} r="3.2" fill={c as string} stroke={L} strokeWidth="1.2" />
          ))}
          <path d="M18 26 q6 -6 12 0 q6 -6 12 0" stroke={L} strokeWidth="1.8" fill="none" />
        </>
      )}
    </svg>
  )
}
