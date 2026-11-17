/**
 * 방 소품 그림(#705). 그림 키 + 색마다 SVG를 코드로 그린다(파일 없음, 방 그림체: 남청 선·평면 색).
 * 서 있는 소품은 화면을 보는 그림판(뭉치처럼), 까는 소품은 바닥에 붙은 그림, 거는 소품은 벽에 붙은 그림으로 쓴다.
 * 모양·색은 여기만 고치면 칸 그림·내 방·친구 방이 같이 바뀐다(서버·계약과 상관없음).
 */
const L = '#1F4E6B'
const SW = 3
type Pal = Record<string, string>

/** 소품 색: [색 키, 화면 이름, 칠할 색들]. 첫 번째가 기본 색(서버 color null·모르는 색) */
export type DecorColor = { key: string; label: string; swatch: string; pal: Pal }
const c = (key: string, label: string, swatch: string, pal: Pal): DecorColor => ({ key, label, swatch, pal })

/**
 * 공통 8색 팔레트(사용자 결정 2026-11-17 "ㄱ 공통 8색"): [키, 이름, 기본, 진한, 연한]. 방 그림체와 어울리는 색만 둬 어떻게 골라도 방이 지저분하지 않게.
 * 색을 바꿀 수 있는 부분(화분·갓·쿠션 소파·러그·시계 테두리·액자 틀·선반·인형)에 모두 쓴다. 섞인 색 소품은 아래 묶음 색.
 */
const BASE: [string, string, string, string, string][] = [
  ['sky', '하늘', '#9CCBEF', '#6FA8D6', '#DDEEFB'],
  ['pink', '분홍', '#F7AEC4', '#E28DA8', '#FFE3EC'],
  ['yellow', '노랑', '#FFDF6B', '#F2C230', '#FFF4C2'],
  ['green', '초록', '#9CCB8C', '#6FAE5F', '#DDF2D4'],
  ['purple', '보라', '#C9A8F0', '#9F7FD6', '#EEE3FB'],
  ['orange', '주황', '#F2A65A', '#D9853A', '#FDE3C8'],
  ['white', '흰', '#F4F1EA', '#D9D3C6', '#FFFFFF'],
  ['navy', '남색', '#5A6FB8', '#3D4C86', '#D3DAF2'],
]
const WOOD: [string, string, string, string, string] = ['wood', '나무', '#D9A46F', '#B97C48', '#F1DCC2']
/** 8색(+나무)으로 그 소품 색 목록을 만든다. first: 기본 색 키(맨 앞으로) */
function palette(first: string, paint: (main: string, dark: string, light: string) => Pal, withWood = false): DecorColor[] {
  const list = [...(withWood ? [WOOD] : []), ...BASE].map(([key, label, main, dark, light]) => c(key, label, main, paint(main, dark, light)))
  return [...list.filter((x) => x.key === first), ...list.filter((x) => x.key !== first)]
}
export const DECOR_COLORS: Record<string, DecorColor[]> = {
  'room/decor-plant.svg': palette('orange', (m, d) => ({ pot: m, pot2: d })),
  'room/decor-plant-big.svg': palette('white', (m, d) => ({ pot: m, pot2: d })),
  // 꽃과 화분이 같은 색(사용자 의견 2026-11-17 "화분 색깔도 바꾸면 되잖아", 놓은 것마다 색은 하나라 세트)
  'room/decor-cactus.svg': palette('pink', (m, d) => ({ flower: m, flower2: d, pot: m, pot2: d })),
  'room/decor-lamp.svg': palette('yellow', (m, d) => ({ shade: m, shade2: d })),
  'room/decor-doll.svg': palette('white', (_m, _d, l) => ({ body: l })),
  'room/decor-beanbag.svg': palette('sky', (m, d) => ({ bag: m, bag2: d })),
  'room/decor-rug.svg': palette('sky', (m, d, l) => ({ a: m, b: l, d })),
  'room/decor-rug-square.svg': palette('green', (m, d, l) => ({ a: l, b: m, edge: d })),
  'room/decor-rug-star.svg': palette('yellow', (m, _d, l) => ({ a: m, b: l })),
  'room/decor-clock.svg': palette('sky', (m) => ({ rim: m })),
  'room/decor-picture.svg': palette('yellow', (m) => ({ frame: m }), true),
  'room/decor-shelf.svg': palette('wood', (m, d) => ({ wood: m, wood2: d }), true),
  // 섞인 색 소품: 묶음 색 4가지
  'room/decor-books.svg': [
    c('mix', '알록달록', '#E3533C', { b1: '#E3533C', b2: '#7FC8D8', b3: '#FFD84D' }),
    c('pastel', '파스텔', '#F7AEC4', { b1: '#F7AEC4', b2: '#C9A8F0', b3: '#FFF4C2' }),
    c('sea', '바다', '#6FA8D6', { b1: '#3D4C86', b2: '#6FA8D6', b3: '#DDEEFB' }),
    c('forest', '숲', '#6FAE5F', { b1: '#6FAE5F', b2: '#B97C48', b3: '#DDF2D4' }),
  ],
  'room/decor-lights.svg': [
    c('rainbow', '알록달록', '#F7AEC4', { b1: '#FFD84D', b2: '#F7AEC4', b3: '#9CCB8C', b4: '#7FC8D8', b5: '#C9A8F0' }),
    c('warm', '노란 불빛', '#FFD84D', { b1: '#FFE07A', b2: '#FFD84D', b3: '#FFE07A', b4: '#FFD84D', b5: '#FFE07A' }),
    c('pastel', '파스텔', '#EEE3FB', { b1: '#FFE3EC', b2: '#EEE3FB', b3: '#DDF2D4', b4: '#DDEEFB', b5: '#FFF4C2' }),
    c('cool', '하늘빛', '#9CCBEF', { b1: '#DDEEFB', b2: '#9CCBEF', b3: '#FFFFFF', b4: '#9CCBEF', b5: '#DDEEFB' }),
  ],
  'room/decor-garland.svg': [
    c('pastel', '파스텔', '#C9A8F0', { f1: '#F7AEC4', f2: '#FFE07A', f3: '#9FDCC6', f4: '#C9A8F0', f5: '#9CCBEF' }),
    c('bright', '선명한', '#E3533C', { f1: '#E3533C', f2: '#FFC93C', f3: '#4FAE5A', f4: '#3E8FD8', f5: '#F27FA5' }),
    c('pink', '분홍빛', '#F7AEC4', { f1: '#F7AEC4', f2: '#FFE3EC', f3: '#E28DA8', f4: '#FFFFFF', f5: '#F7AEC4' }),
    c('sea', '바다', '#6FA8D6', { f1: '#3D4C86', f2: '#9CCBEF', f3: '#FFFFFF', f4: '#6FA8D6', f5: '#DDEEFB' }),
  ],
}
export const decorColors = (assetKey: string | null | undefined) => DECOR_COLORS[assetKey ?? ''] ?? []
/** 그 소품에서 쓸 색(모르는 색·null은 기본 색) */
export const decorColor = (assetKey: string | null | undefined, color: string | null | undefined) => {
  const list = decorColors(assetKey)
  return list.find((x) => x.key === color) ?? list[0]
}

type Art = { w: number; h: number; body: string }
const svg = (a: Art) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${a.w} ${a.h}">${a.body}</svg>`
const g = (attrs: string, inner: string) => `<g ${attrs}>${inner}</g>`
const st = `stroke="${L}" stroke-width="${SW}" stroke-linejoin="round" stroke-linecap="round"`

function art(key: string, p: Pal): Art | null {
  switch (key) {
    case 'room/decor-plant.svg': // 작은 화분: 둥근 잎 다섯 장
      return { w: 100, h: 120, body: g(st,
        `<path d="M50 70 C48 58 46 48 40 38" fill="none"/><path d="M50 70 C52 56 58 46 66 40" fill="none"/><path d="M50 70 V44" fill="none"/>` +
        `<ellipse cx="34" cy="40" rx="15" ry="10" transform="rotate(-30 34 40)" fill="#7DBE6B"/><ellipse cx="68" cy="38" rx="15" ry="10" transform="rotate(28 68 38)" fill="#8FCB7C"/>` +
        `<ellipse cx="50" cy="28" rx="11" ry="16" fill="#9CD68A"/><ellipse cx="30" cy="58" rx="13" ry="8" transform="rotate(-12 30 58)" fill="#8FCB7C"/><ellipse cx="70" cy="58" rx="13" ry="8" transform="rotate(14 70 58)" fill="#7DBE6B"/>` +
        `<path d="M28 74 H72 L66 112 H34 Z" fill="${p.pot}"/><rect x="24" y="68" width="52" height="11" rx="4" fill="${p.pot2}"/>`) }
    case 'room/decor-plant-big.svg': { // 큰 화분(몬스테라): 구멍 뚫린 하트 모양 큰 잎 다섯 장
      // 잎 하나(밑동이 (0,0), 위로 뻗음). 구멍은 같은 길 안의 작은 조각(evenodd로 뚫림)
      const LEAF = 'M0 0 C-30 -6 -36 -48 0 -62 C36 -48 30 -6 0 0 Z' +
        ' M-25 -20 L-9 -24 L-9 -28 L-26 -27 Z M-28 -36 L-9 -38 L-9 -42 L-27 -44 Z M25 -20 L9 -24 L9 -28 L26 -27 Z M28 -36 L9 -38 L9 -42 L27 -44 Z'
      const leaf = (x: number, y: number, rot: number, sc: number, fill: string) =>
        `<g transform="translate(${x} ${y}) rotate(${rot}) scale(${sc})"><path d="${LEAF}" fill="${fill}" fill-rule="evenodd"/><path d="M0 -4 V-56" fill="none" stroke="#2E7A44" stroke-width="2"/></g>`
      // 옆 잎이 잘리지 않게 그림 칸을 넓히고(160) 가운데로 옮김
      return { w: 160, h: 204, body: `<g transform="translate(20 4)">` + g(st,
        `<path d="M60 146 C50 130 40 118 34 108 M60 146 C70 128 80 116 86 102 M60 146 V76 M60 146 C44 140 34 136 26 134 M60 146 C76 140 88 136 96 132" fill="none" stroke="#3F8A4F"/>` +
        leaf(26, 134, -72, 0.72, '#3F9A55') + leaf(96, 132, 72, 0.72, '#3F9A55') + leaf(34, 108, -36, 0.95, '#4FAE5A') + leaf(86, 102, 36, 0.95, '#4FAE5A') + leaf(60, 76, 0, 1.05, '#5CBF66') +
        `<path d="M34 150 H86 L80 196 H40 Z" fill="${p.pot}"/><rect x="30" y="142" width="60" height="13" rx="5" fill="${p.pot2}"/>`) + '</g>' }
    }
    case 'room/decor-cactus.svg': { // 선인장: 팔 둘 + 꽃잎 여섯 장 꽃(위) + 작은 꽃(오른팔), 화분도 같은 색
      const flower = (cx: number, cy: number, r: number) =>
        Array.from({ length: 6 }, (_, k) => `<ellipse cx="${cx}" cy="${cy - r}" rx="${r * 0.55}" ry="${r * 0.95}" transform="rotate(${k * 60} ${cx} ${cy})" fill="${p.flower}"/>`).join('') +
        Array.from({ length: 6 }, (_, k) => `<path d="M${cx} ${cy - r * 0.45} V${cy - r * 1.35}" transform="rotate(${k * 60} ${cx} ${cy})" fill="none" stroke="${p.flower2}" stroke-width="1.6"/>`).join('') +
        `<circle cx="${cx}" cy="${cy}" r="${r * 0.5}" fill="#FFD84D"/>` +
        `<circle cx="${cx - r * 0.15}" cy="${cy - r * 0.15}" r="${r * 0.15}" fill="#FFF6C9" stroke="none"/>`
      return { w: 100, h: 124, body: g(st,
        `<path d="M38 80 V44 C38 30 62 30 62 44 V80 Z" fill="#7DBE6B"/><path d="M38 62 H28 C22 62 22 48 28 48 V44" fill="none"/><path d="M62 56 H72 C78 56 78 42 72 42 V38" fill="none"/>` +
        `<path d="M44 44 V74 M50 38 V76 M56 44 V74" fill="none" stroke="#5E9E4E" stroke-width="2"/>` +
        flower(50, 24, 10) + flower(72, 37, 5) +
        `<path d="M30 80 H70 L65 116 H35 Z" fill="${p.pot}"/><rect x="26" y="74" width="48" height="10" rx="4" fill="${p.pot2}"/>`) }
    }
    case 'room/decor-lamp.svg': // 스탠드 조명: 큰 갓 + 굵은 기둥 + 넓은 받침 + 불빛
      return { w: 120, h: 210, body:
        `<ellipse cx="60" cy="96" rx="40" ry="18" fill="#FFF6C9" opacity=".75"/>` + g(st,
        `<ellipse cx="60" cy="198" rx="36" ry="9" fill="#7A8290"/><rect x="54" y="72" width="12" height="126" rx="5" fill="#8A93A3"/>` +
        `<path d="M18 78 L36 18 H84 L102 78 Z" fill="${p.shade}"/><path d="M26 64 H94" fill="none" stroke="${p.shade2}" stroke-width="5"/>` +
        `<path d="M44 24 L34 66" fill="none" stroke="#FFFFFF" stroke-width="4" opacity=".55"/>`) }
    case 'room/decor-doll.svg': // 뭉치 인형: 구름 모양 몸 + 눈·볼
      return { w: 110, h: 110, body: g(st,
        `<path d="M24 92 C8 90 6 70 18 64 C8 54 16 36 32 40 C34 24 54 18 62 30 C74 18 96 26 92 44 C106 50 104 72 90 76 C98 90 80 100 70 94 C62 104 40 104 34 94 C30 96 26 96 24 92 Z" fill="${p.body}"/>` +
        `<circle cx="44" cy="60" r="4.5" fill="${L}" stroke="none"/><circle cx="68" cy="60" r="4.5" fill="${L}" stroke="none"/>` +
        `<ellipse cx="36" cy="70" rx="6" ry="4" fill="#F7AEC4" stroke="none"/><ellipse cx="76" cy="70" rx="6" ry="4" fill="#F7AEC4" stroke="none"/>` +
        `<path d="M52 68 Q56 72 60 68" fill="none"/>`) }
    case 'room/decor-books.svg': // 쌓은 책 셋 + 위에 펼친 책
      return { w: 110, h: 80, body: g(st,
        `<rect x="10" y="56" width="88" height="18" rx="3" fill="${p.b1}"/><rect x="18" y="38" width="78" height="18" rx="3" fill="${p.b2}"/><rect x="8" y="20" width="84" height="18" rx="3" fill="${p.b3}"/>` +
        `<path d="M20 56 V74 M86 38 V56 M18 20 V38" fill="none" stroke="#FFFDF6" stroke-width="3"/>` +
        `<path d="M30 20 C40 10 50 10 56 16 C62 10 72 10 82 20 Z" fill="#FFFDF6"/>`) }
    case 'room/decor-beanbag.svg': // 쿠션 소파(그림 키는 예전 이름 beanbag 그대로): 말랑한 덩어리 + 눌린 자리
      return { w: 170, h: 110, body: g(st,
        `<path d="M14 92 C4 70 16 40 44 28 C70 16 104 16 128 28 C156 42 168 70 156 92 C140 106 30 106 14 92 Z" fill="${p.bag}"/>` +
        `<path d="M46 60 C64 48 104 48 124 60" fill="none" stroke="${p.bag2}" stroke-width="5"/><ellipse cx="62" cy="40" rx="16" ry="7" fill="#FFFFFF" opacity=".45" stroke="none"/>`) }
    case 'room/decor-rug.svg': // 동그란 러그(위에서 본 모습)
      return { w: 200, h: 200, body: g(st,
        `<circle cx="100" cy="100" r="92" fill="${p.a}"/><circle cx="100" cy="100" r="66" fill="${p.b}" stroke-dasharray="8 7"/><circle cx="100" cy="100" r="30" fill="${p.d}"/>`) }
    case 'room/decor-rug-square.svg': { // 네모 러그(체크) + 술
      let checks = ''
      for (let i = 0; i < 6; i++) for (let j = 0; j < 4; j++) if ((i + j) % 2 === 0) checks += `<rect x="${30 + i * 40}" y="${20 + j * 40}" width="40" height="40" fill="${p.b}" stroke="none"/>`
      const fringe = Array.from({ length: 9 }, (_, i) => `<path d="M${36 + i * 28} 180 V192 M${36 + i * 28} 20 V8" fill="none" stroke="${p.edge}"/>`).join('')
      return { w: 300, h: 200, body: `${fringe}<rect x="30" y="20" width="240" height="160" rx="6" fill="${p.a}" ${st}/>${checks}<rect x="30" y="20" width="240" height="160" rx="6" fill="none" ${st}/>` }
    }
    case 'room/decor-rug-star.svg': { // 별 러그
      const pts = Array.from({ length: 10 }, (_, i) => { const r = i % 2 ? 40 : 92; const t = -Math.PI / 2 + (i * Math.PI) / 5; return `${(100 + r * Math.cos(t)).toFixed(1)},${(104 + r * Math.sin(t)).toFixed(1)}` }).join(' ')
      return { w: 200, h: 200, body: g(st, `<polygon points="${pts}" fill="${p.a}"/><circle cx="100" cy="104" r="22" fill="${p.b}" stroke-dasharray="5 5"/>`) }
    }
    case 'room/decor-lights.svg': { // 줄 조명: 굵은 줄 + 큰 전구 일곱
      const bulbs = [[30, 30], [72, 46], [114, 56], [150, 58], [186, 56], [228, 46], [270, 30]]
      const cols = [p.b1, p.b2, p.b3, p.b4, p.b5, p.b1, p.b2]
      return { w: 300, h: 110, body: g(st, `<path d="M8 14 Q150 96 292 14" fill="none" stroke-width="4"/>` +
        bulbs.map(([x, y], i) => `<rect x="${x - 5}" y="${y - 6}" width="10" height="10" rx="2" fill="${L}" stroke="none"/><path d="M${x} ${y + 2} C${x - 14} ${y + 14} ${x - 10} ${y + 36} ${x} ${y + 36} C${x + 10} ${y + 36} ${x + 14} ${y + 14} ${x} ${y + 2} Z" fill="${cols[i]}"/><ellipse cx="${x - 4}" cy="${y + 18}" rx="3" ry="6" fill="#FFFFFF" opacity=".6" stroke="none"/>`).join('')) }
    }
    case 'room/decor-garland.svg': { // 깃발 가랜드: 삼각 깃발 일곱
      const xs = [24, 64, 104, 150, 196, 236, 276]
      const ys = [16, 28, 36, 39, 36, 28, 16]
      const cols = [p.f1, p.f2, p.f3, p.f4, p.f5, p.f1, p.f2]
      return { w: 300, h: 100, body: g(st, `<path d="M6 10 Q150 70 294 10" fill="none" stroke-width="4"/>` +
        xs.map((x, i) => `<path d="M${x - 16} ${ys[i]} L${x + 16} ${ys[i]} L${x} ${ys[i] + 40} Z" fill="${cols[i]}"/>`).join('')) }
    }
    case 'room/decor-clock.svg': // 벽시계
      return { w: 100, h: 100, body: g(st, `<circle cx="50" cy="50" r="42" fill="${p.rim}"/><circle cx="50" cy="50" r="32" fill="#FFFDF6"/>` +
        [0, 90, 180, 270].map((d) => `<path d="M50 22 V28" transform="rotate(${d} 50 50)" fill="none"/>`).join('') +
        `<path d="M50 50 V30 M50 50 L64 58" fill="none" stroke-width="4"/><circle cx="50" cy="50" r="3.5" fill="${L}"/>`) }
    case 'room/decor-picture.svg': // 작은 그림 액자: 해와 언덕
      return { w: 100, h: 90, body: g(st, `<rect x="6" y="6" width="88" height="78" rx="4" fill="${p.frame}"/><rect x="16" y="16" width="68" height="58" fill="#CFE6FA"/>` +
        `<circle cx="64" cy="32" r="8" fill="#FFD84D"/><path d="M16 74 C30 50 46 50 58 62 C66 54 76 54 84 62 V74 Z" fill="#9CCB8C"/>`) }
    case 'room/decor-shelf.svg': // 벽 선반 + 작은 화분·책
      return { w: 200, h: 100, body: g(st,
        `<path d="M40 70 V92 L56 70 M160 70 V92 L144 70" fill="none" stroke="${p.wood2}" stroke-width="5"/><rect x="14" y="62" width="172" height="12" rx="3" fill="${p.wood}"/>` +
        `<path d="M40 62 H64 L60 40 H44 Z" fill="#E28D5B"/><ellipse cx="46" cy="30" rx="9" ry="12" fill="#8FCB7C"/><ellipse cx="58" cy="28" rx="8" ry="11" fill="#7DBE6B"/>` +
        `<rect x="110" y="30" width="12" height="32" fill="#7FC8D8"/><rect x="124" y="24" width="12" height="38" fill="#FFD84D"/><rect x="138" y="34" width="12" height="28" transform="rotate(10 144 48)" fill="#F7AEC4"/>`) }
    default:
      return null
  }
}

/** 그 소품·색의 SVG 문자열(그림 목록에 없으면 null) */
export function decorSvg(assetKey: string | null | undefined, color?: string | null) {
  const a = art(assetKey ?? '', decorColor(assetKey, color)?.pal ?? {})
  return a ? { svg: svg(a), w: a.w, h: a.h } : null
}
/** CSS 배경으로 쓰는 data URI */
export function decorBg(assetKey: string | null | undefined, color?: string | null, fit: 'contain' | '100% 100%' = 'contain') {
  const s = decorSvg(assetKey, color)
  return s ? `url("data:image/svg+xml;utf8,${encodeURIComponent(s.svg)}") center / ${fit} no-repeat` : 'none'
}

// ---------- 입체 소품 부품(#705, 사용자 의견 2026-11-17 "방은 3D인데 소품은 너무 2D") ----------
const uri = (body: string, w: number, h: number, keep = 'none') =>
  `url("data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="${keep}">${body}</svg>`)}") center / 100% 100% no-repeat`
/** 화분 윗면: 테두리 안쪽 흙 */
export function soilBg(rim: string) {
  return uri(`<rect x="1.5" y="1.5" width="97" height="97" rx="6" fill="${rim}" stroke="${L}" stroke-width="3" vector-effect="non-scaling-stroke"/>` +
    `<rect x="14" y="14" width="72" height="72" rx="10" fill="#7A5230" stroke="${L}" stroke-width="2" vector-effect="non-scaling-stroke"/>` +
    `<circle cx="36" cy="40" r="4" fill="#5E3E22"/><circle cx="62" cy="58" r="3" fill="#5E3E22"/>`, 100, 100)
}
/** 작은 화분 잎(화분 없이): X자로 엇갈려 세우는 그림판 한 장 */
export function plantLeavesBg() {
  return uri(g(st,
    `<path d="M50 78 C48 64 46 54 40 44" fill="none"/><path d="M50 78 C52 62 58 52 66 46" fill="none"/><path d="M50 78 V50" fill="none"/>` +
    `<ellipse cx="34" cy="46" rx="15" ry="10" transform="rotate(-30 34 46)" fill="#7DBE6B"/><ellipse cx="68" cy="44" rx="15" ry="10" transform="rotate(28 68 44)" fill="#8FCB7C"/>` +
    `<ellipse cx="50" cy="32" rx="11" ry="16" fill="#9CD68A"/><ellipse cx="28" cy="64" rx="13" ry="8" transform="rotate(-12 28 64)" fill="#8FCB7C"/><ellipse cx="72" cy="64" rx="13" ry="8" transform="rotate(14 72 64)" fill="#7DBE6B"/>`), 100, 80, 'xMidYMax meet')
}

/** 큰 화분(몬스테라) 잎만: 엇갈려 세우는 그림판 */
export function bigLeavesBg() {
  const LEAF = 'M0 0 C-30 -6 -36 -48 0 -62 C36 -48 30 -6 0 0 Z' +
    ' M-25 -20 L-9 -24 L-9 -28 L-26 -27 Z M-28 -36 L-9 -38 L-9 -42 L-27 -44 Z M25 -20 L9 -24 L9 -28 L26 -27 Z M28 -36 L9 -38 L9 -42 L27 -44 Z'
  const leaf = (x: number, y: number, rot: number, sc: number, fill: string) =>
    `<g transform="translate(${x} ${y}) rotate(${rot}) scale(${sc})"><path d="${LEAF}" fill="${fill}" fill-rule="evenodd"/><path d="M0 -4 V-56" fill="none" stroke="#2E7A44" stroke-width="2"/></g>`
  return uri(`<g transform="translate(20 0)">` + g(st,
    `<path d="M60 150 C50 132 40 118 34 108 M60 150 C70 130 80 116 86 102 M60 150 V76 M60 150 C44 142 34 138 26 134 M60 150 C76 142 88 138 96 132" fill="none" stroke="#3F8A4F"/>` +
    leaf(26, 134, -72, 0.72, '#3F9A55') + leaf(96, 132, 72, 0.72, '#3F9A55') + leaf(34, 108, -36, 0.95, '#4FAE5A') + leaf(86, 102, 36, 0.95, '#4FAE5A') + leaf(60, 76, 0, 1.05, '#5CBF66')) + '</g>', 160, 152, 'xMidYMax meet')
}
/** 선인장 몸통·팔·꽃만(화분 없이): 엇갈려 세우는 그림판 */
export function cactusBg(p: Pal) {
  const flower = (cx: number, cy: number, r: number) =>
    Array.from({ length: 6 }, (_, k) => `<ellipse cx="${cx}" cy="${cy - r}" rx="${r * 0.55}" ry="${r * 0.95}" transform="rotate(${k * 60} ${cx} ${cy})" fill="${p.flower}"/>`).join('') +
    `<circle cx="${cx}" cy="${cy}" r="${r * 0.5}" fill="#FFD84D"/>`
  return uri(g(st,
    `<path d="M38 96 V44 C38 30 62 30 62 44 V96 Z" fill="#7DBE6B"/><path d="M38 66 H28 C22 66 22 52 28 52 V46" fill="none" stroke-width="5"/><path d="M62 60 H72 C78 60 78 46 72 46 V40" fill="none" stroke-width="5"/>` +
    `<path d="M44 44 V92 M50 38 V94 M56 44 V92" fill="none" stroke="#5E9E4E" stroke-width="2"/>` + flower(50, 24, 10) + flower(72, 38, 5)), 100, 98, 'xMidYMax meet')
}
/** 시계 앞판(눈금·바늘) */
export function clockFaceBg(rim: string) {
  return uri(g(st, `<circle cx="50" cy="50" r="46" fill="${rim}"/><circle cx="50" cy="50" r="35" fill="#FFFDF6"/>` +
    [0, 90, 180, 270].map((d) => `<path d="M50 20 V27" transform="rotate(${d} 50 50)" fill="none"/>`).join('') +
    `<path d="M50 50 V28 M50 50 L66 59" fill="none" stroke-width="5"/><circle cx="50" cy="50" r="4" fill="${L}"/>`), 100, 100, 'xMidYMid meet')
}
/** 작은 그림 앞판(틀 안 풍경) */
export function pictureBg(frame: string) {
  return uri(g(st, `<rect x="2" y="2" width="96" height="86" fill="${frame}"/><rect x="13" y="13" width="74" height="64" fill="#CFE6FA"/>` +
    `<circle cx="66" cy="32" r="9" fill="#FFD84D"/><path d="M13 77 C28 50 46 50 58 64 C67 55 78 55 87 64 V77 Z" fill="#9CCB8C"/>`), 100, 90)
}
/** 쌓은 책 앞면(표지 + 책등 띠) */
export const bookCoverBg = (color: string) => `linear-gradient(90deg, transparent 0 10%, rgba(255,253,246,.85) 10% 15%, transparent 15%), ${color}`
/** 책 옆면(종이 결) */
export const PAGES_BG = 'repeating-linear-gradient(0deg, #FFFDF6 0 3px, #E6DCC6 3px 4px)'
