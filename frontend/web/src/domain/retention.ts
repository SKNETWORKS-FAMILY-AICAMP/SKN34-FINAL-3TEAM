import type { ThinkingType } from './classroom.ts'
import { THINKING_ORDER, COMPANIONS, THEMES } from './studentLook.ts'
import type { CompanionId, ThemeId } from './studentLook.ts'

/**
 * 2026-11-06 결정(에픽 #396)의 학생 참여 기능: 포인트·꾸미기(P21·P22), 주간 테마(P23), 커뮤니티(P20).
 * 서버 계약은 API 명세 2.9~2.11·3.12(구현 예정)를 따른다. 점수·순위가 아닌 참여 기록만 다룬다.
 */

// ---------- 포인트 (API 명세 2.10) ----------
export type PointEventType =
  | 'MISSION_COMPLETED'
  | 'REVIEW_VIEWED'
  | 'COMMUNITY_POSTED'
  | 'REACTION_GIVEN'
  | 'THEME_COMPLETED'
  | 'UNLOCK'
export const POINT_EVENT_LABELS: Record<PointEventType, string> = {
  MISSION_COMPLETED: '미션 학습 완료',
  REVIEW_VIEWED: '되돌아보기',
  COMMUNITY_POSTED: '내 풀이 공유',
  REACTION_GIVEN: '친구 생각에 반응',
  THEME_COMPLETED: '주간 테마 완주',
  UNLOCK: '꾸미기 해금',
}
/** 초기 적립값(P21). 실제 값은 서버 `reward_rule` 데이터라 화면은 안내에만 쓴다. */
export const POINT_RULES: { type: Exclude<PointEventType, 'UNLOCK'>; amount: number; note: string }[] = [
  { type: 'MISSION_COMPLETED', amount: 10, note: '미션마다 처음 한 번' },
  { type: 'REVIEW_VIEWED', amount: 10, note: '토·일 되돌아보기, 한 주에 한 번' },
  { type: 'COMMUNITY_POSTED', amount: 5, note: '마무리한 풀이가 공유될 때' },
  { type: 'REACTION_GIVEN', amount: 1, note: '하루 5번까지' },
  { type: 'THEME_COMPLETED', amount: 30, note: '월~금 문제를 그날 끝내고 되돌아보기까지' },
]
export interface PointEvent {
  eventType: PointEventType
  amount: number
  createdAt: string
}
export interface Points {
  balance: number
  items: PointEvent[]
}
const isPointEvent = (v: unknown): v is PointEventType => typeof v === 'string' && v in POINT_EVENT_LABELS

export function readPoints(raw: unknown): Points {
  const v = (raw ?? {}) as { balance?: unknown; items?: unknown }
  const items = Array.isArray(v.items) ? v.items : []
  return {
    balance: typeof v.balance === 'number' && Number.isFinite(v.balance) ? v.balance : 0,
    items: items.flatMap((x) => {
      const e = (x ?? {}) as Record<string, unknown>
      return isPointEvent(e.eventType) && typeof e.amount === 'number' && typeof e.createdAt === 'string'
        ? [{ eventType: e.eventType, amount: e.amount, createdAt: e.createdAt }]
        : []
    }),
  }
}

// ---------- 꾸미기 해금·아이템 (API 명세 2.10·3.12) ----------
export type ItemSlot = 'HAT' | 'OUTFIT' | 'ACCESSORY' | 'BACKGROUND'
export type LookSlot = 'THEME' | 'COMPANION' | ItemSlot
export const ITEM_SLOTS: ItemSlot[] = ['HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND']
export const SLOT_LABELS: Record<LookSlot, string> = {
  THEME: '테마',
  COMPANION: '캐릭터',
  HAT: '모자',
  OUTFIT: '옷',
  ACCESSORY: '소품',
  BACKGROUND: '배경',
}
export type Equipped = Record<ItemSlot, string | null>
export const NO_EQUIPPED: Equipped = { HAT: null, OUTFIT: null, ACCESSORY: null, BACKGROUND: null }
export const FREE_THEME: ThemeId = 'lake'
export const FREE_COMPANION: CompanionId = 'mungchi'
/** 해금값은 코드 상수(P22): 테마 100, 캐릭터 150. 서버 목록이 우선이고 이 값은 목업·안내용이다. */
export const THEME_PRICE = 100
export const COMPANION_PRICE = 150
export const themeKey = (id: ThemeId) => `THEME:${id}`
export const companionKey = (id: CompanionId) => `COMPANION:${id}`

export interface LookItem {
  itemKey: string
  slot: LookSlot
  name: string
  pricePoints: number
  unlocked: boolean
  onSale: boolean
}
const isSlot = (v: unknown): v is LookSlot => typeof v === 'string' && v in SLOT_LABELS

export function readLookItems(raw: unknown): LookItem[] {
  const items = Array.isArray((raw as { items?: unknown })?.items) ? (raw as { items: unknown[] }).items : []
  return items.flatMap((x) => {
    const v = (x ?? {}) as Record<string, unknown>
    if (typeof v.itemKey !== 'string' || !isSlot(v.slot)) return []
    return [
      {
        itemKey: v.itemKey,
        slot: v.slot,
        name: typeof v.name === 'string' ? v.name : v.itemKey,
        pricePoints: typeof v.pricePoints === 'number' ? v.pricePoints : 0,
        unlocked: v.unlocked === true,
        onSale: v.onSale !== false,
      },
    ]
  })
}
export function readEquipped(raw: unknown): Equipped {
  const v = (raw ?? {}) as Partial<Record<ItemSlot, unknown>>
  return Object.fromEntries(
    ITEM_SLOTS.map((s) => [s, typeof v[s] === 'string' ? (v[s] as string) : null]),
  ) as Equipped
}
/** 테마·캐릭터는 목록에 없을 때도 무료 항목은 열려 있다고 본다(목록 실패가 기본 모습을 막지 않게). */
export function isLookUnlocked(items: LookItem[] | undefined, itemKey: string) {
  if (itemKey === themeKey(FREE_THEME) || itemKey === companionKey(FREE_COMPANION)) return true
  return items?.find((i) => i.itemKey === itemKey)?.unlocked ?? false
}
/** 기본 테마·캐릭터 목록(목업과 안내). 실제 잠금 여부는 서버 `unlocked`. */
export function baseLookCatalog(): Omit<LookItem, 'unlocked'>[] {
  return [
    ...Object.values(THEMES).map((t) => ({
      itemKey: themeKey(t.id),
      slot: 'THEME' as const,
      name: t.title,
      pricePoints: t.id === FREE_THEME ? 0 : THEME_PRICE,
      onSale: true,
    })),
    ...COMPANIONS.map((c) => ({
      itemKey: companionKey(c.id),
      slot: 'COMPANION' as const,
      name: c.label,
      pricePoints: c.id === FREE_COMPANION ? 0 : COMPANION_PRICE,
      onSale: true,
    })),
  ]
}

// ---------- 주간 테마·되돌아보기 (API 명세 2.11) ----------
export type ThemeDay = 'MON' | 'TUE' | 'WED' | 'THU' | 'FRI'
export const THEME_DAYS: ThemeDay[] = ['MON', 'TUE', 'WED', 'THU', 'FRI']
export const DAY_LABELS: Record<ThemeDay, string> = { MON: '월', TUE: '화', WED: '수', THU: '목', FRI: '금' }
export type DayState = 'LOCKED' | 'OPEN' | 'CLOSED'
export type AttemptContext = 'THEME_DAY' | 'THEME_REVIEW' | 'EXTRA'
export interface WeeklyThemeDay {
  day: ThemeDay
  missionId: string
  thinkingType: ThinkingType
  state: DayState
  attemptStatus: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED'
  title?: string
}
export interface WeeklyTheme {
  themeId: string
  weekStart: string
  title: string
  intro: string | null
  reused: boolean
  days: WeeklyThemeDay[]
  review: { open: boolean; missions: { missionId: string; completed: boolean; missed: boolean; title?: string }[] }
  completed: boolean
}
const isDay = (v: unknown): v is ThemeDay => typeof v === 'string' && (THEME_DAYS as string[]).includes(v)
const isType = (v: unknown): v is ThinkingType => typeof v === 'string' && (THINKING_ORDER as string[]).includes(v)
const pick = <T extends string>(v: unknown, values: readonly T[], fallback: T): T =>
  typeof v === 'string' && (values as readonly string[]).includes(v) ? (v as T) : fallback

/** 이번 주 테마. 테마가 없으면(404·빈 응답) null을 돌려 기존 홈만 보이게 한다. */
export function readWeeklyTheme(raw: unknown): WeeklyTheme | null {
  const v = (raw ?? {}) as Record<string, unknown>
  if (typeof v.themeId !== 'string' || !Array.isArray(v.days)) return null
  const review = (v.review ?? {}) as Record<string, unknown>
  return {
    themeId: v.themeId,
    weekStart: typeof v.weekStart === 'string' ? v.weekStart : '',
    title: typeof v.title === 'string' ? v.title : '이번 주 테마',
    intro: typeof v.intro === 'string' && v.intro ? v.intro : null,
    reused: v.reused === true,
    days: v.days.flatMap((x) => {
      const d = (x ?? {}) as Record<string, unknown>
      if (!isDay(d.day) || typeof d.missionId !== 'string' || !isType(d.thinkingType)) return []
      return [
        {
          day: d.day,
          missionId: d.missionId,
          thinkingType: d.thinkingType,
          state: pick(d.state, ['LOCKED', 'OPEN', 'CLOSED'] as const, 'LOCKED'),
          attemptStatus: pick(d.attemptStatus, ['NOT_STARTED', 'IN_PROGRESS', 'COMPLETED'] as const, 'NOT_STARTED'),
          ...(typeof d.title === 'string' ? { title: d.title } : {}),
        },
      ]
    }),
    review: {
      open: review.open === true,
      missions: (Array.isArray(review.missions) ? review.missions : []).flatMap((x) => {
        const m = (x ?? {}) as Record<string, unknown>
        return typeof m.missionId === 'string'
          ? [{ missionId: m.missionId, completed: m.completed === true, missed: m.missed === true, ...(typeof m.title === 'string' ? { title: m.title } : {}) }]
          : []
      }),
    },
    completed: v.completed === true,
  }
}
/** KST 기준 요일(월=0 … 일=6). */
export function kstWeekday(now = new Date()) {
  const day = new Date(now.getTime() + 9 * 3600_000).getUTCDay()
  return (day + 6) % 7
}
export const todayThemeDay = (theme: WeeklyTheme) => theme.days.find((d) => d.state === 'OPEN') ?? null
export function dayStatusText(d: WeeklyThemeDay) {
  if (d.attemptStatus === 'COMPLETED') return '끝냈어요'
  if (d.state === 'OPEN') return d.attemptStatus === 'IN_PROGRESS' ? '이어서 하기' : '오늘 문제'
  if (d.state === 'LOCKED') return '아직 열리지 않았어요'
  return d.attemptStatus === 'IN_PROGRESS' ? '이어서 할 수 있어요' : '지난 요일'
}

// ---------- 커뮤니티 (API 명세 2.9) ----------
export type Reaction = 'NEW_IDEA' | 'CLEAR_REASON' | 'DIFFERENT_VIEW' | 'WANT_MORE'
export const REACTIONS: Reaction[] = ['NEW_IDEA', 'CLEAR_REASON', 'DIFFERENT_VIEW', 'WANT_MORE']
export const REACTION_LABELS: Record<Reaction, string> = {
  NEW_IDEA: '새로운 생각이야',
  CLEAR_REASON: '까닭이 잘 보여',
  DIFFERENT_VIEW: '나랑 다르게 생각했네',
  WANT_MORE: '더 알고 싶어',
}
export type PostStatus = 'VISIBLE' | 'HIDDEN_SETTING' | 'HIDDEN_REPORT' | 'REMOVED'
export const POST_STATUS_LABELS: Record<PostStatus, string> = {
  VISIBLE: '공개 중',
  HIDDEN_SETTING: '공개 설정이 꺼져 비공개',
  HIDDEN_REPORT: '신고되어 확인 중',
  REMOVED: '숨김 처리됨',
}
export interface CommunitySettings {
  enabled: boolean
  consentGranted: boolean
  updatedAt: string | null
}
export interface CommunityPost {
  postId: string
  author: { nickname: string; companion: CompanionId }
  answer: string
  myReactions: Reaction[]
  createdAt: string
}
export interface MyCommunityPost {
  postId: string
  missionId: string
  missionTitle: string
  answer: string
  status: PostStatus
  reactions: Record<Reaction, number>
  createdAt: string
}
const isReaction = (v: unknown): v is Reaction => typeof v === 'string' && (REACTIONS as string[]).includes(v)
export function readCommunitySettings(raw: unknown): CommunitySettings {
  const v = (raw ?? {}) as Record<string, unknown>
  return { enabled: v.enabled === true, consentGranted: v.consentGranted === true, updatedAt: typeof v.updatedAt === 'string' ? v.updatedAt : null }
}
/** 커뮤니티 답 원문은 서버가 `content`를 그대로 줄 수 있어 글로 읽을 수 있는 부분만 보인다. */
export function answerText(answer: unknown): string {
  if (typeof answer === 'string') return answer
  const v = (answer ?? {}) as Record<string, unknown>
  if (typeof v.text === 'string') return v.text
  if (Array.isArray(v.steps)) return v.steps.filter((s) => typeof s === 'string').join('\n')
  return ''
}
export function readCommunityPosts(raw: unknown): CommunityPost[] {
  const items = Array.isArray((raw as { items?: unknown })?.items) ? (raw as { items: unknown[] }).items : []
  return items.flatMap((x) => {
    const v = (x ?? {}) as Record<string, unknown>
    if (typeof v.postId !== 'string') return []
    const author = (v.author ?? {}) as Record<string, unknown>
    const look = (author.look ?? {}) as Record<string, unknown>
    const companion = COMPANIONS.find((c) => c.id === look.companion)?.id ?? FREE_COMPANION
    return [
      {
        postId: v.postId,
        author: { nickname: typeof author.nickname === 'string' ? author.nickname : '친구', companion },
        answer: answerText(v.answer),
        myReactions: Array.isArray(v.myReactions) ? v.myReactions.filter(isReaction) : [],
        createdAt: typeof v.createdAt === 'string' ? v.createdAt : '',
      },
    ]
  })
}
export function readMyPosts(raw: unknown): MyCommunityPost[] {
  const items = Array.isArray((raw as { items?: unknown })?.items) ? (raw as { items: unknown[] }).items : []
  return items.flatMap((x) => {
    const v = (x ?? {}) as Record<string, unknown>
    if (typeof v.postId !== 'string') return []
    const counts = (v.reactions ?? {}) as Record<string, unknown>
    return [
      {
        postId: v.postId,
        missionId: typeof v.missionId === 'string' ? v.missionId : '',
        missionTitle: typeof v.missionTitle === 'string' ? v.missionTitle : '미션',
        answer: answerText(v.answer),
        status: pick(v.status, ['VISIBLE', 'HIDDEN_SETTING', 'HIDDEN_REPORT', 'REMOVED'] as const, 'VISIBLE'),
        reactions: Object.fromEntries(
          REACTIONS.map((r) => [r, typeof counts[r] === 'number' ? (counts[r] as number) : 0]),
        ) as Record<Reaction, number>,
        createdAt: typeof v.createdAt === 'string' ? v.createdAt : '',
      },
    ]
  })
}
