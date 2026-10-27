import type { Attempt, Mission, StudentHome, ThinkingType } from './classroom.ts'
import { thinkingLabels } from './classroom.ts'

/** 학생 화면 꾸미기 설정 (API 명세 3.12). 학습 기록·판정과 무관한 표시 설정이다. */
export type ThemeId = 'lake' | 'forest' | 'factory' | 'space' | 'sea'
export type CompanionId = 'mungchi' | 'tori' | 'mongdol' | 'kongi' | 'monggeul'
export interface StudentLook {
  theme: ThemeId
  companion: CompanionId
  updatedAt: string | null
}
export interface Theme {
  id: ThemeId
  name: string
  /** 홈 이름 (생각 호수) */
  title: string
  sub: string
  /** 생각 유형 한 곳을 부르는 말 (섬, 공터…) */
  place: string
  bg: string
  shade: string
  light: string
  light2: string
  top: string
  side: string
}

export const THEMES: Record<ThemeId, Theme> = {
  lake: { id: 'lake', name: '호수', title: '생각 호수', sub: '생각이 뭉치는 호수', place: '섬', bg: '#2E6F73', shade: '#367A7E', light: '#A8DDD4', light2: '#C6EAE1', top: '#F4ECDC', side: '#CDBB95' },
  forest: { id: 'forest', name: '숲', title: '생각 숲', sub: '생각이 자라는 숲', place: '공터', bg: '#2F5B3B', shade: '#386B45', light: '#9CCB8C', light2: '#C4E3B5', top: '#EFE6CC', side: '#B9A57A' },
  factory: { id: 'factory', name: '공장', title: '생각 공장', sub: '생각을 만드는 공장', place: '작업대', bg: '#3B4452', shade: '#454F5E', light: '#E9B949', light2: '#F4D88A', top: '#ECE7DD', side: '#A9A196' },
  space: { id: 'space', name: '소행성', title: '생각 우주', sub: '생각이 떠다니는 우주', place: '소행성', bg: '#1B2238', shade: '#262F4C', light: '#F2C14E', light2: '#FFF3C4', top: '#D9D2C4', side: '#9C9384' },
  sea: { id: 'sea', name: '바닷속', title: '생각 바다', sub: '생각이 헤엄치는 바다', place: '산호섬', bg: '#0F4C66', shade: '#155A77', light: '#7FC8D8', light2: '#B5E3EC', top: '#F3E3D0', side: '#D49A84' },
}
export const COMPANIONS: { id: CompanionId; label: string; desc: string }[] = [
  { id: 'mungchi', label: '뭉치', desc: '생각이 뭉친 친구' },
  { id: 'tori', label: '토리', desc: '작은 도토리' },
  { id: 'mongdol', label: '몽돌', desc: '둥근 조약돌' },
  { id: 'kongi', label: '콩이', desc: '강낭콩 새싹' },
  { id: 'monggeul', label: '몽글', desc: '몽글몽글 구름' },
]
export const DEFAULT_LOOK: StudentLook = { theme: 'lake', companion: 'mungchi', updatedAt: null }

export const isThemeId = (v: unknown): v is ThemeId => typeof v === 'string' && v in THEMES
export const isCompanionId = (v: unknown): v is CompanionId =>
  COMPANIONS.some((c) => c.id === v)
export const companionLabel = (id: CompanionId) =>
  (COMPANIONS.find((c) => c.id === id) ?? COMPANIONS[0]).label

/** 서버 응답을 검사해 알 수 없는 값은 기본값으로 둔다(화면이 깨지지 않게). */
export function readLook(raw: unknown): StudentLook {
  const v = (raw ?? {}) as Partial<Record<keyof StudentLook, unknown>>
  return {
    theme: isThemeId(v.theme) ? v.theme : DEFAULT_LOOK.theme,
    companion: isCompanionId(v.companion) ? v.companion : DEFAULT_LOOK.companion,
    updatedAt: typeof v.updatedAt === 'string' ? v.updatedAt : null,
  }
}

/** 생각 지도에서 다섯 유형의 깃발 색. 서로 밝기도 달라 색만으로 구분하지 않게 이름을 함께 쓴다. */
export const THINKING_ORDER: ThinkingType[] = ['ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT']
export const thinkingHue: Record<ThinkingType, string> = {
  ANALYZE: '#2779A7',
  EVALUATE: '#B8551C',
  CREATE: '#5E8C00',
  SOLVE: '#987654',
  REFLECT: '#6B4E8C',
}

export interface Island {
  type: ThinkingType
  label: string
  /** 이 유형에서 끝낸 미션 수 (홈 응답의 미션 상태로 센다. 레벨·점수가 아니다) */
  done: number
  /** 이 유형에서 시작할 수 있는 미션 수 */
  open: number
  today: boolean
}

/** 오늘 가 볼 미션: 이어할 시도 → 진행 중 → 시작 전 순서. 없으면 null. */
export function todayMission(home: Pick<StudentHome, 'resume' | 'missions'>): Mission | null {
  if (home.resume) return home.resume.mission
  return (
    home.missions.find((m) => m.status === 'IN_PROGRESS') ??
    home.missions.find((m) => (m.status ?? 'NOT_STARTED') === 'NOT_STARTED') ??
    null
  )
}

export function islands(home: Pick<StudentHome, 'resume' | 'missions'>): Island[] {
  const today = todayMission(home)?.thinkingType
  return THINKING_ORDER.map((type) => {
    const ms = home.missions.filter((m) => m.thinkingType === type)
    return {
      type,
      label: thinkingLabels[type],
      done: ms.filter((m) => m.status === 'COMPLETED').length,
      open: ms.filter((m) => m.status !== 'COMPLETED').length,
      today: type === today,
    }
  })
}

/** 미션 진행 단계: 내 생각 쓰기 → 한 걸음 더(되묻기) → 돌아보기(마무리 후). */
export type MissionStage = 'write' | 'more' | 'reflect'
export const STAGE_LABELS: Record<MissionStage, string> = {
  write: '내 생각 쓰기',
  more: '한 걸음 더',
  reflect: '돌아보기',
}
export function missionStage(a: Pick<Attempt, 'finishedAt' | 'answers'>): MissionStage {
  if (a.finishedAt) return 'reflect'
  return a.answers.length ? 'more' : 'write'
}

export const isThinkingType = (v: string | null): v is ThinkingType =>
  !!v && (THINKING_ORDER as string[]).includes(v)
