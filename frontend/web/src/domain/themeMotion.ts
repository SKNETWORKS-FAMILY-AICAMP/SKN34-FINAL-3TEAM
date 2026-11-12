/**
 * 장면 움직임 형식 v1 (api-spec 4.2 `/internal/theme-drafts` motions, ai OpenAPI `ThemeMotion`).
 * learning·core는 칸 검사 없이 그대로 전달하므로 웹이 읽을 때 검사하고, 모르는 칸·잘못된 값은 버린다.
 * 좌표(x·y)는 그림 너비·높이 기준 %, 시간은 초. 관리자 미리보기(#441)와 학생 이야기 화면(#440)이 같이 쓴다.
 */
export interface MotionPoint { x: number; y: number; zoom: number }
export interface MotionCaption { start: number; end: number; text: string }
export interface MotionSpot { x: number; y: number; label: string; line: string; evidence: boolean }
export interface MotionEffect { shape: string; color: string; count: number; size: number; direction: string; speed: number; opacity: number }
export interface ThemeMotion {
  version: number
  transition: { kind: string; seconds: number } | null
  camera: { from: MotionPoint; to: MotionPoint; seconds: number } | null
  speakers: Record<string, MotionPoint>
  effects: MotionEffect[]
  captions: MotionCaption[]
  spots: MotionSpot[]
}

const num = (v: unknown, min: number, max: number) => typeof v === 'number' && Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : null
const obj = (v: unknown) => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const list = (v: unknown) => (Array.isArray(v) ? v : [])
function point(v: unknown): MotionPoint | null {
  const o = obj(v)
  const x = num(o?.x, 0, 100), y = num(o?.y, 0, 100), zoom = num(o?.zoom ?? 1, 1, 4)
  return x === null || y === null || zoom === null ? null : { x, y, zoom }
}

/** 형식 v1이 아니거나 비어 있으면 null(움직임 없이 정지 그림) */
export function readThemeMotion(raw: unknown): ThemeMotion | null {
  const o = obj(raw)
  if (!o || o.version !== 1) return null
  const t = obj(o.transition), c = obj(o.camera)
  const from = point(c?.from), to = point(c?.to), seconds = num(c?.seconds, 0.1, 120)
  const speakers: Record<string, MotionPoint> = {}
  for (const [name, value] of Object.entries(obj(o.speakers) ?? {})) {
    const p = point(value)
    if (p && name) speakers[name] = p
  }
  return {
    version: 1,
    transition: t && typeof t.kind === 'string' && num(t.seconds, 0, 10) !== null ? { kind: t.kind, seconds: num(t.seconds, 0, 10)! } : null,
    camera: from && to && seconds !== null ? { from, to, seconds } : null,
    speakers,
    effects: list(o.effects).flatMap((e) => {
      const v = obj(e)
      if (!v || typeof v.shape !== 'string') return []
      return [{ shape: v.shape, color: typeof v.color === 'string' ? v.color : '#ffffff', count: num(v.count, 0, 40) ?? 8,
        size: num(v.size, 1, 40) ?? 6, direction: typeof v.direction === 'string' ? v.direction : 'down', speed: num(v.speed, 0, 10) ?? 1,
        opacity: num(v.opacity, 0, 1) ?? 0.7 }]
    }),
    captions: list(o.captions).flatMap((e) => {
      const v = obj(e), start = num(v?.start, 0, 600), end = num(v?.end, 0, 600)
      return v && typeof v.text === 'string' && v.text && start !== null && end !== null && end > start ? [{ start, end, text: v.text }] : []
    }).sort((a, b) => a.start - b.start),
    spots: list(o.spots).flatMap((e) => {
      const v = obj(e), x = num(v?.x, 0, 100), y = num(v?.y, 0, 100)
      return v && x !== null && y !== null && typeof v.label === 'string' && v.label
        ? [{ x, y, label: v.label, line: typeof v.line === 'string' ? v.line : '', evidence: v.evidence === true }] : []
    }),
  }
}

/** 재생 시각(초)에 보일 컷 문구. 겹치면 나중에 시작한 문구 */
export function captionAt(motion: ThemeMotion | null, seconds: number) {
  return motion?.captions.filter((c) => c.start <= seconds && seconds < c.end).at(-1)?.text ?? null
}
