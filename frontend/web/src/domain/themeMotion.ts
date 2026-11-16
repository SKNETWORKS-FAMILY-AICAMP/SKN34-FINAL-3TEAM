/**
 * 장면 움직임 형식 v1 (ai OpenAPI `ThemeMotion`, api-spec 4.2 `/internal/theme-drafts` motions, ai `models.ThemeMotion`).
 * learning·core는 칸 검사 없이 그대로 저장·전달하므로(learning `ThemeMotion` additionalProperties) 웹이 읽을 때 검사한다.
 * 형식 v1 범위를 하나라도 벗어나면 null(움직임 없이 그림만, #440 "값이 없거나 형식이 틀리면 그림만"). 모르는 칸은 버린다.
 * 좌표(x·y)는 그림 너비·높이 %, 시간은 초. 학생 이야기 화면·문제 장면(#440)과 관리자 미리보기(#441)가 같이 쓴다.
 * 예전에는 이 파일(느슨하게 잘라 맞춤)과 domain/retention.ts(엄격) 두 벌이었고, 이 파일은 effects.direction을 'up'·'down' 글자로,
 * zoom을 1~4로 읽어 ai가 보내는 숫자 각도를 무시했다(#440에서 하나로 합침).
 */
export interface MotionPoint { x: number; y: number; zoom: number }
export type MotionShape = 'circle' | 'leaf' | 'petal' | 'drop' | 'star' | 'snow' | 'bubble' | 'confetti'
export type MotionTransition = 'none' | 'fade' | 'slide-left' | 'slide-right' | 'zoom'
export interface MotionEffect {
  shape: MotionShape
  color: string
  count: number
  /** 그림 너비 % */
  size: number
  /** 도(0~359). 0은 아래로 떨어짐 */
  direction: number
  /** 초당 그림 높이 % */
  speed: number
  opacity: number
}
export interface MotionCaption { start: number; end: number; text: string }
export interface MotionSpot { x: number; y: number; label: string; line: string; evidence: boolean }
export interface ThemeMotion {
  version: 1
  transition: { kind: MotionTransition; seconds: number }
  camera: { from: MotionPoint; to: MotionPoint; seconds: number } | null
  speakers: Record<string, MotionPoint>
  effects: MotionEffect[]
  /** 시작·종료 영상(그림 장면) 위에 웹이 띄우는 컷 문구(초). */
  captions: MotionCaption[]
  /** 요일 장면 살펴보기(선택 칸). 시작·종료는 빈 배열. 학생 화면에는 보이지 않음(사용자 결정 2026-11-13). */
  spots: MotionSpot[]
}

const SHAPES: MotionShape[] = ['circle', 'leaf', 'petal', 'drop', 'star', 'snow', 'bubble', 'confetti']
const TRANSITIONS: MotionTransition[] = ['none', 'fade', 'slide-left', 'slide-right', 'zoom']
const inRange = (v: unknown, min: number, max: number): v is number => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max
const record = (v: unknown) => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const isPoint = (v: unknown): v is MotionPoint => {
  const p = record(v)
  return !!p && inRange(p.x, 0, 100) && inRange(p.y, 0, 100) && inRange(p.zoom, 1, 1.4)
}
const point = (p: MotionPoint): MotionPoint => ({ x: p.x, y: p.y, zoom: p.zoom })

/** 형식 v1이 아니거나 범위를 벗어난 칸이 하나라도 있으면 null(정지 그림) */
export function readThemeMotion(raw: unknown): ThemeMotion | null {
  const v = record(raw)
  if (!v || v.version !== 1) return null
  const transition = record(v.transition)
  const camera = v.camera === null ? null : record(v.camera)
  const speakers = record(v.speakers)
  if (!transition || !TRANSITIONS.includes(transition.kind as MotionTransition) || !inRange(transition.seconds, 0.3, 1.2)) return null
  if (v.camera !== null && (!camera || !isPoint(camera.from) || !isPoint(camera.to) || !inRange(camera.seconds, 8, 20))) return null
  if (!speakers || !Object.values(speakers).every(isPoint)) return null
  if (!Array.isArray(v.effects) || v.effects.length > 2 || !Array.isArray(v.captions) || v.captions.length > 8) return null
  const spots = v.spots === undefined ? [] : v.spots
  if (!Array.isArray(spots) || spots.length > 3) return null
  const effects = v.effects.map((x) => record(x) ?? {})
  if (!effects.every((e) => SHAPES.includes(e.shape as MotionShape) && typeof e.color === 'string' && /^#[0-9A-Fa-f]{6}$/.test(e.color) &&
      Number.isInteger(e.count) && inRange(e.count, 1, 20) && inRange(e.size, 1, 6) && Number.isInteger(e.direction) && inRange(e.direction, 0, 359) &&
      inRange(e.speed, 2, 20) && inRange(e.opacity, 0.2, 0.8))) return null
  const captions = v.captions.map((x) => record(x) ?? {})
  if (!captions.every((c) => inRange(c.start, 0, Infinity) && inRange(c.end, 0, Infinity) && (c.end as number) >= (c.start as number) &&
      typeof c.text === 'string' && c.text.length <= 30)) return null
  const marks = spots.map((x) => record(x) ?? {})
  if (!marks.every((s) => inRange(s.x, 0, 100) && inRange(s.y, 0, 100) && typeof s.label === 'string' && s.label.length >= 1 && s.label.length <= 10 &&
      typeof s.line === 'string' && s.line.length >= 1 && s.line.length <= 30 && typeof s.evidence === 'boolean')) return null
  return {
    version: 1,
    transition: { kind: transition.kind as MotionTransition, seconds: transition.seconds as number },
    camera: camera ? { from: point(camera.from as MotionPoint), to: point(camera.to as MotionPoint), seconds: camera.seconds as number } : null,
    speakers: Object.fromEntries(Object.entries(speakers as Record<string, MotionPoint>).map(([k, p]) => [k, point(p)])),
    effects: effects.map((e) => ({
      shape: e.shape as MotionShape, color: e.color as string, count: e.count as number, size: e.size as number,
      direction: e.direction as number, speed: e.speed as number, opacity: e.opacity as number,
    })),
    captions: captions.map((c) => ({ start: c.start as number, end: c.end as number, text: c.text as string })).sort((a, b) => a.start - b.start),
    spots: marks.map((s) => ({ x: s.x as number, y: s.y as number, label: s.label as string, line: s.line as string, evidence: s.evidence as boolean })),
  }
}

/** 재생 시각(초)에 보일 컷 문구. 겹치면 나중에 시작한 문구 */
export function captionAt(motion: ThemeMotion | null, seconds: number) {
  return motion?.captions.filter((c) => c.start <= seconds && seconds < c.end).at(-1)?.text ?? null
}

/**
 * 효과 방향(도) → 화면 단위 벡터. 계약은 "0은 아래로 떨어짐"만 정해 회전 방향은 웹 기준안:
 * 화면에서 시계 방향(CSS rotate와 같음) — 90 왼쪽, 180 위로 떠오름, 270 오른쪽.
 */
export function effectVector(direction: number) {
  const rad = (direction * Math.PI) / 180
  const round = (n: number) => Math.round(n * 1e6) / 1e6 || 0
  return { dx: round(-Math.sin(rad)), dy: round(Math.cos(rad)) }
}

export interface EffectParticle {
  /** 입자 중심의 시작·끝 위치(px, 그림 왼쪽 위 기준). 시작·끝 모두 그림 밖 */
  x0: number
  y0: number
  x1: number
  y1: number
  /** 입자 한 변(px) = 그림 너비 × size% */
  size: number
  /** 한 번 가로지르는 시간(초) = 이동 거리 ÷ (그림 높이 × speed%/초) */
  seconds: number
  /** 음수 지연(초): 처음부터 길 위에 흩어져 보이게 */
  delay: number
}

/**
 * 효과 한 층의 입자 경로. 그림(w×h px)을 방향대로 가로지르게, 들어오는 쪽 가장자리를 따라 고르게 흩어 놓는다.
 * 무작위 대신 황금비 순서라 같은 값이면 늘 같은 자리(다시 그려도 튀지 않음).
 */
export function effectParticles(fx: MotionEffect, w: number, h: number): EffectParticle[] {
  if (!(w > 0 && h > 0)) return []
  const { dx, dy } = effectVector(fx.direction)
  const size = (fx.size / 100) * w
  const along = Math.abs(dx) * w + Math.abs(dy) * h
  const across = Math.abs(dy) * w + Math.abs(dx) * h
  const travel = along + 2 * size
  const seconds = travel / ((fx.speed / 100) * h)
  const frac = (n: number) => n - Math.floor(n)
  return Array.from({ length: fx.count }, (_, n) => {
    const u = (frac((n + 0.5) * 0.6180339887) - 0.5) * across
    const x0 = w / 2 - (dx * travel) / 2 - dy * u
    const y0 = h / 2 - (dy * travel) / 2 + dx * u
    return { x0, y0, x1: x0 + dx * travel, y1: y0 + dy * travel, size, seconds, delay: -frac(n * 0.3819660113 + 0.5 / fx.count) * seconds }
  })
}
