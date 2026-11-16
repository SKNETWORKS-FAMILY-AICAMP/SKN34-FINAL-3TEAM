import { createElement } from 'react'
import type { ReactElement } from 'react'
import type { FriendId } from '../../../domain/studentLook.ts'

/**
 * 뭉치 친구들 12종 그림(#648). 설계 캔버스 `Mungchi.dc.html`의 SVG(200×220 좌표)를 그대로 옮겼다.
 * JSX 없이 그림 표만 두어 단위 시험(node --test)에서도 그려 볼 수 있게 했고, `Companion.tsx`가 이 표를 쓴다.
 * 옷·모자·소품은 캔버스처럼 몸에 그려 넣지 않고 착용 그림 파일(roomAssets.ts WEAR_ANCHORS)로 겹친다.
 */

/** 친구 그림이 모두 들어가는 정사각형 영역(발·팔·새싹까지). 모자처럼 밖으로 나가는 것은 svg overflow로 보인다 */
export const FRIEND_VIEWBOX = '8 32 184 184'

const LINE = '#3A2A20',
  CHEEK = '#F7B6A6',
  WHITE = '#FFFFFF'

type Attrs = Record<string, string | number>
type Shape = [tag: 'g' | 'circle' | 'ellipse' | 'path' | 'rect', attrs: Attrs, children?: Shape[]]

const circle = (cx: number, cy: number, r: number, attrs: Attrs = {}): Shape => ['circle', { cx, cy, r, ...attrs }]
const ellipse = (cx: number, cy: number, rx: number, ry: number, attrs: Attrs = {}): Shape => ['ellipse', { cx, cy, rx, ry, ...attrs }]
const path = (d: string, attrs: Attrs): Shape => ['path', { d, ...attrs }]
const group = (attrs: Attrs, children: Shape[]): Shape => ['g', attrs, children]
const stroke = (color: string, width: number, extra: Attrs = {}): Attrs =>
  ({ stroke: color, strokeWidth: width, fill: 'none', strokeLinecap: 'round', ...extra })

/** 솜뭉치 몸 둘레 솜 10개 */
const COTTON_PUFFS: [number, number][] = [[158, 128], [147, 162], [118, 183], [82, 183], [53, 162], [42, 128], [53, 94], [82, 73], [118, 73], [147, 94]]
/** 구름뭉치 구름 5개 [x, y, 안쪽 반지름] */
const CLOUD_PUFFS: [number, number, number][] = [[54, 122, 37], [100, 94, 45], [146, 122, 37], [72, 158, 35], [128, 158, 35]]
const STAR = 'M100 52 L124 104 L176 110 L138 146 L150 196 L100 170 L50 196 L62 146 L24 110 L76 104Z'
const PETALS = [0, 45, 90, 135, 180, 225, 270, 315].map((deg) =>
  ellipse(100, 72, 30, 38, deg ? { transform: `rotate(${deg} 100 130)` } : {}))

/** 친구마다 다른 몸. 발(뒤)과 얼굴(앞)은 모두 같다 */
const BODIES: Record<FriendId, Shape[]> = {
  cotton: [
    group({ fill: LINE }, COTTON_PUFFS.map(([x, y]) => circle(x, y, 25))),
    group({ fill: '#FFF6E9' }, [...COTTON_PUFFS.map(([x, y]) => circle(x, y, 21)), circle(100, 128, 62)]),
  ],
  cloud: [
    group({ fill: LINE }, CLOUD_PUFFS.map(([x, y, r]) => circle(x, y, r + 4))),
    group({ fill: '#CFE6FA' }, [...CLOUD_PUFFS.map(([x, y, r]) => circle(x, y, r)), circle(100, 130, 48)]),
  ],
  snow: [
    path('M36 128 L12 104 M16 122 L24 112 M164 128 L188 104 M184 122 L176 112', stroke('#7A5234', 5)),
    circle(100, 130, 66, { fill: WHITE, stroke: LINE, strokeWidth: 4 }),
    path('M52 170 C76 192 124 192 148 170', stroke('#BFDDF5', 10)),
    path('M100 52 V82 M86 60 L114 74 M114 60 L86 74', stroke('#7CB8E0', 4)),
  ],
  yarn: [
    path('M158 170 C186 176 192 196 174 204', stroke('#E0708F', 6)),
    circle(100, 130, 66, { fill: '#F7AEC4', stroke: LINE, strokeWidth: 4 }),
    path('M44 100 C76 76 124 74 158 96 M38 124 C60 92 88 74 122 68 M162 124 C142 92 112 74 80 68', stroke('#E0708F', 4)),
  ],
  moss: [
    path('M36 152 C30 98 66 64 100 64 C134 64 170 98 164 152 C160 188 130 196 100 196 C70 196 40 188 36 152Z', { fill: '#B4D69A', stroke: LINE, strokeWidth: 4 }),
    path('M42 112 Q56 92 70 106 Q84 84 100 102 Q116 84 130 106 Q144 92 158 112 C150 78 124 66 100 66 C76 66 50 78 42 112Z', { fill: '#6FAE5F' }),
    path('M100 66 V44 M100 50 C90 36 76 38 72 44 C80 54 92 54 100 50Z M100 50 C110 36 124 38 128 44 C120 54 108 54 100 50Z',
      { fill: '#6FAE5F', stroke: LINE, strokeWidth: 3.5, strokeLinejoin: 'round' }),
  ],
  sand: [
    path('M30 192 C30 120 62 66 100 66 C138 66 170 120 170 192Z', { fill: '#EBCE96', stroke: LINE, strokeWidth: 4, strokeLinejoin: 'round' }),
    group({ fill: '#C9A161' }, [circle(66, 110, 3.5), circle(136, 104, 3.5), circle(48, 170, 3.5), circle(156, 172, 3.5), circle(100, 84, 3.5)]),
    path('M132 186 C128 168 158 168 154 186Z', { fill: CHEEK, stroke: LINE, strokeWidth: 3, strokeLinejoin: 'round' }),
  ],
  star: [
    path(STAR, { fill: LINE, stroke: LINE, strokeWidth: 22, strokeLinejoin: 'round' }),
    path(STAR, { fill: '#FFDE6B', stroke: '#FFDE6B', strokeWidth: 14, strokeLinejoin: 'round' }),
  ],
  foam: [
    circle(164, 72, 15, { fill: '#E6DDF8', stroke: LINE, strokeWidth: 3.5 }),
    circle(36, 88, 10, { fill: '#E6DDF8', stroke: LINE, strokeWidth: 3.5 }),
    circle(100, 130, 66, { fill: '#DDD2F5', stroke: LINE, strokeWidth: 4 }),
    path('M56 104 C62 88 76 78 92 76', stroke(WHITE, 9)),
  ],
  paper: [
    path('M48 90 L84 62 L130 72 L160 64 L170 112 L158 152 L166 192 L118 196 L84 190 L44 194 L52 148 L38 118Z',
      { fill: '#F4F1E8', stroke: LINE, strokeWidth: 4, strokeLinejoin: 'round' }),
    path('M84 62 L92 92 L52 118 M130 72 L122 96 L170 112 M118 196 L128 170 L158 152 M84 190 L76 168 L52 148',
      { stroke: '#C9C2AE', strokeWidth: 3, fill: 'none', strokeLinejoin: 'round' }),
  ],
  petal: [
    group({ transform: 'translate(100 122) scale(.82) translate(-100 -130)' }, [
      group({ fill: '#F9B8CF', stroke: LINE, strokeWidth: 3.5 }, PETALS),
      circle(100, 130, 58, { fill: '#FFF1F5' }),
    ]),
  ],
  cone: [
    path('M100 48 C146 58 166 112 158 156 C152 188 124 198 100 198 C76 198 48 188 42 156 C34 112 54 58 100 48Z', { fill: '#B98857', stroke: LINE, strokeWidth: 4 }),
    path('M52 112 Q76 96 100 112 Q124 96 148 112 M42 152 Q70 136 100 152 Q130 136 158 152 M72 76 Q86 66 100 76 Q114 66 128 76', stroke('#7A5234', 4)),
    ellipse(100, 134, 48, 36, { fill: '#E2BE93' }),
  ],
  ice: [
    ['rect', { x: 38, y: 66, width: 124, height: 130, rx: 26, fill: '#C4ECF7', stroke: LINE, strokeWidth: 4 }],
    path('M56 104 V86 Q56 80 62 80 H84', stroke(WHITE, 9)),
    path('M144 176 L132 182', stroke(WHITE, 7)),
  ],
}

const FEET: Shape[] = [ellipse(80, 205, 17, 9, { fill: LINE }), ellipse(120, 205, 17, 9, { fill: LINE })]
const FACE: Shape[] = [
  circle(78, 130, 10, { fill: LINE }),
  circle(122, 130, 10, { fill: LINE }),
  circle(82, 126, 3.4, { fill: WHITE }),
  circle(126, 126, 3.4, { fill: WHITE }),
  path('M91 148 Q100 158 109 148', stroke(LINE, 4.2)),
  circle(60, 148, 9, { fill: CHEEK }),
  circle(140, 148, 9, { fill: CHEEK }),
]

const draw = (shapes: Shape[], prefix: string): ReactElement[] =>
  shapes.map(([tag, attrs, children], i) =>
    createElement(tag, { key: `${prefix}${i}`, ...attrs }, ...(children ? draw(children, `${prefix}${i}-`) : [])))

/** 보는 방향(설계 캔버스 Mungchi view: front·side·back). 내 방에서 걷는 방향에 따라 바뀐다(사용자 의견 2026-11-16) */
export type FriendView = 'front' | 'side' | 'back'
/** 옆얼굴 위치: 친구마다 눈 높이에서 몸 앞쪽 끝 x(캔버스 EDGE 값) */
const EDGE: Record<FriendId, number> = { cotton: 176, cloud: 178, snow: 164, yarn: 164, moss: 163, sand: 152, star: 146, foam: 164, paper: 164, petal: 146, cone: 160, ice: 160 }
function sideFace(id: FriendId): Shape[] {
  const edge = Math.round(100 + (EDGE[id] - 100) * 0.94)
  return [
    circle(edge - 26, 128, 9.5, { fill: LINE }),
    circle(edge - 23, 124, 3.2, { fill: WHITE }),
    path(`M${edge - 18} 147 Q${edge - 10} 152 ${edge - 6} 145`, stroke(LINE, 4)),
    ellipse(edge - 38, 146, 9, 6.5, { fill: CHEEK, fillOpacity: 0.9 }),
  ]
}
/** 뒷모습: 얼굴 없이 등 위쪽에 옅은 선 하나 */
const BACK: Shape[] = [path('M70 108 Q100 92 130 108', stroke(LINE, 5, { strokeOpacity: 0.18 }))]

/**
 * 옷을 몸 안으로만 그릴 때 쓰는 몸 윤곽(clipPath 안에 넣는 도형). 설계 캔버스 Mungchi의 옷 mask와 같은 역할로,
 * 테두리 선 안쪽 면만 담아 옷이 몸 밖으로 삐져나오지 않고 테두리 선은 그대로 보이게 한다(사용자 의견 2026-11-16 "캐릭터마다 잘 맞게").
 * clipPath 안에는 g를 쓸 수 없어 변환은 도형마다 붙인다. 옆모습은 몸 그림과 같이 가로 0.94배
 */
const SILHOUETTES: Record<FriendId, Shape[]> = {
  cotton: [...COTTON_PUFFS.map(([x, y]) => circle(x, y, 21)), circle(100, 128, 62)],
  cloud: [...CLOUD_PUFFS.map(([x, y, r]) => circle(x, y, r)), circle(100, 130, 48)],
  snow: [circle(100, 130, 64)],
  yarn: [circle(100, 130, 64)],
  moss: [path('M36 152 C30 98 66 64 100 64 C134 64 170 98 164 152 C160 188 130 196 100 196 C70 196 40 188 36 152Z', {})],
  sand: [path('M30 192 C30 120 62 66 100 66 C138 66 170 120 170 192Z', {})],
  star: [path(STAR, {})],
  foam: [circle(100, 130, 64)],
  paper: [path('M48 90 L84 62 L130 72 L160 64 L170 112 L158 152 L166 192 L118 196 L84 190 L44 194 L52 148 L38 118Z', {})],
  petal: [...[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => ellipse(100, 72, 30, 38, { transform: `translate(100 122) scale(.82) translate(-100 -130)${deg ? ` rotate(${deg} 100 130)` : ''}` })),
    circle(100, 130, 58, { transform: 'translate(100 122) scale(.82) translate(-100 -130)' })],
  cone: [path('M100 48 C146 58 166 112 158 156 C152 188 124 198 100 198 C76 198 48 188 42 156 C34 112 54 58 100 48Z', {})],
  ice: [['rect', { x: 40, y: 68, width: 120, height: 126, rx: 24 }]],
}
const SIDE = 'translate(100 0) scale(.94 1) translate(-100 0)'
export function friendSilhouette(id: FriendId, view: FriendView = 'front'): ReactElement[] {
  const shapes = view === 'side'
    ? SILHOUETTES[id].map(([tag, attrs]): Shape => [tag, { ...attrs, transform: `${SIDE}${attrs.transform ? ` ${attrs.transform}` : ''}` }])
    : SILHOUETTES[id]
  return draw(shapes, 's')
}
/** 소품을 드는 자리(x): 친구 몸 앞쪽 끝(옆얼굴과 같은 EDGE 값)에 붙인다. 옆모습은 몸과 같이 0.94배 */
export const frontEdge = (id: FriendId, view: FriendView = 'front') =>
  view === 'side' ? Math.round(100 + (EDGE[id] - 100) * 0.94) : EDGE[id]

/** 친구 한 명의 몸 그림(발 → 몸 → 얼굴). `<svg viewBox={FRIEND_VIEWBOX}>` 안에 넣는다. 옆모습은 오른쪽을 본다(왼쪽은 scaleX(-1)) */
export function friendArt(id: FriendId, view: FriendView = 'front'): ReactElement {
  const body = draw(BODIES[id], 'b')
  return createElement('g', { className: 'st-friend-art', 'data-friend': id, 'data-view': view },
    ...draw(FEET, 'f'),
    ...(view === 'side' ? [createElement('g', { key: 'side-body', transform: 'translate(100 0) scale(.94 1) translate(-100 0)' }, ...body)] : body),
    ...draw(view === 'front' ? FACE : view === 'side' ? sideFace(id) : BACK, 'c'))
}
