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
  | 'THEME_ON_TIME'
  | 'THEME_FINISHED'
  | 'UNLOCK'
export const POINT_EVENT_LABELS: Record<PointEventType, string> = {
  MISSION_COMPLETED: '미션 학습 완료',
  REVIEW_VIEWED: '되돌아보기',
  COMMUNITY_POSTED: '내 풀이 공유',
  REACTION_GIVEN: '친구 생각에 반응',
  THEME_COMPLETED: '주간 테마 개근',
  THEME_ON_TIME: '테마 문제 당일 풀이',
  THEME_FINISHED: '주간 테마 완주',
  UNLOCK: '꾸미기 해금',
}
/**
 * 적립값(P21, #485 2026-11-10 개정). 실제 값은 서버 `reward_rule` 데이터라 화면은 안내에만 쓴다.
 * 당일 풀이·주간 완주는 learning #484가 판정 칸(`days[].completedOnDay`·`finished`)을 내보내 적립된다(#506 "준비 중" 표시 제거)
 */
export const POINT_RULES: { type: Exclude<PointEventType, 'UNLOCK'>; amount: number; note: string }[] = [
  { type: 'MISSION_COMPLETED', amount: 10, note: '미션마다 처음 한 번' },
  { type: 'REVIEW_VIEWED', amount: 10, note: '토·일 되돌아보기, 한 주에 한 번' },
  { type: 'COMMUNITY_POSTED', amount: 5, note: '마무리한 풀이가 공유될 때' },
  { type: 'REACTION_GIVEN', amount: 1, note: '하루 5번까지' },
  { type: 'THEME_ON_TIME', amount: 5, note: '테마 문제를 공개된 그날 끝내면' },
  { type: 'THEME_COMPLETED', amount: 30, note: '월~금 문제를 모두 그날 끝내면' },
  { type: 'THEME_FINISHED', amount: 10, note: '토요일까지 테마 문제 5개를 끝내면' },
]
export interface PointEvent {
  eventType: PointEventType
  amount: number
  createdAt: string
}
export interface Points {
  balance: number
  items: PointEvent[]
  page: number
  size: number
  totalElements: number
}
const isPointEvent = (v: unknown): v is PointEventType => typeof v === 'string' && v in POINT_EVENT_LABELS
const nonNegativeInteger = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0
function rewardContractError(): never {
  throw new Error('포인트·꾸미기 정보를 확인하지 못했어요. 다시 확인해 주세요.')
}

export function readPoints(raw: unknown): Points {
  const v = (raw ?? {}) as Record<keyof Points, unknown>
  if (!nonNegativeInteger(v.balance) || !Array.isArray(v.items) || !nonNegativeInteger(v.page) ||
      !nonNegativeInteger(v.size) || v.size < 1 || v.size > 100 || !nonNegativeInteger(v.totalElements) ||
      v.items.length > v.size || v.items.length > v.totalElements) return rewardContractError()
  return {
    balance: v.balance, page: v.page, size: v.size, totalElements: v.totalElements,
    items: v.items.flatMap((x) => {
      const e = (x ?? {}) as Record<string, unknown>
      if (!Number.isSafeInteger(e.amount) || typeof e.createdAt !== 'string' || !Number.isFinite(Date.parse(e.createdAt)))
        return rewardContractError()
      return isPointEvent(e.eventType) && typeof e.amount === 'number' && typeof e.createdAt === 'string'
        ? [{ eventType: e.eventType, amount: e.amount, createdAt: e.createdAt }]
        : []
    }),
  }
}

// ---------- 꾸미기 해금·아이템 (API 명세 2.10·3.12) ----------
/** 캐릭터·배경 4칸(P22). 배경은 내 방 벽지로도 쓴다(P27). */
export type CharacterSlot = 'HAT' | 'OUTFIT' | 'ACCESSORY' | 'BACKGROUND'
/** 내 방 가구 스킨 칸(P27, API 명세 2.10 2026-11-12). 가구 1개 = 착용 칸 1개 */
export type FurnitureSlot = 'DESK' | 'WALL' | 'WARDROBE'
export type ItemSlot = CharacterSlot | FurnitureSlot
export type LookSlot = 'THEME' | 'COMPANION' | ItemSlot
export const ITEM_SLOTS: CharacterSlot[] = ['HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND']
export const FURNITURE_SLOTS: FurnitureSlot[] = ['DESK', 'WALL', 'WARDROBE']
/** 관리자 아이템 등록에서 고르는 칸 전체 */
export const ALL_ITEM_SLOTS: ItemSlot[] = [...ITEM_SLOTS, ...FURNITURE_SLOTS]
export const SLOT_LABELS: Record<LookSlot, string> = {
  THEME: '테마',
  COMPANION: '캐릭터',
  HAT: '모자',
  OUTFIT: '옷',
  ACCESSORY: '소품',
  BACKGROUND: '배경',
  DESK: '학습 책상',
  WALL: '추억의 벽',
  WARDROBE: '옷장',
}
/**
 * 착용 칸. 가구 칸은 서버가 알려 준 때만 둔다: 가구 칸을 모르는 서버(core #555 전)에 보내면
 * 422라 기존 꾸미기 저장이 깨지지 않게 한다. 가구 칸이 비면(null·없음) 기본 스킨.
 */
export type Equipped = Record<CharacterSlot, string | null> & Partial<Record<FurnitureSlot, string | null>>
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
  assetKey: string | null
}
const isSlot = (v: unknown): v is LookSlot => typeof v === 'string' && v in SLOT_LABELS

export function readLookItems(raw: unknown): LookItem[] {
  const items = (raw as { items?: unknown })?.items
  if (!Array.isArray(items)) return rewardContractError()
  return items.flatMap((x) => {
    const v = (x ?? {}) as Record<string, unknown>
    if (typeof v.itemKey !== 'string' || !isSlot(v.slot)) return []
    if (!v.itemKey || typeof v.name !== 'string' || !nonNegativeInteger(v.pricePoints) ||
        typeof v.unlocked !== 'boolean' || typeof v.onSale !== 'boolean' ||
        (v.assetKey !== null && typeof v.assetKey !== 'string')) return rewardContractError()
    return [
      {
        itemKey: v.itemKey,
        slot: v.slot,
        name: v.name, pricePoints: v.pricePoints, unlocked: v.unlocked, onSale: v.onSale,
        assetKey: v.assetKey,
      },
    ]
  })
}
export interface UnlockResult { itemKey: string; unlocked: true; balance: number }
export function readUnlockResult(raw: unknown, itemKey: string): UnlockResult {
  const value = (raw ?? {}) as Partial<UnlockResult>
  if (value.itemKey !== itemKey || value.unlocked !== true || !nonNegativeInteger(value.balance)) return rewardContractError()
  return { itemKey, unlocked: true, balance: value.balance }
}
export function readEquipped(raw: unknown): Equipped {
  const v = (raw ?? {}) as Partial<Record<ItemSlot, unknown>>
  const value = (s: ItemSlot) => (typeof v[s] === 'string' && v[s] ? (v[s] as string) : null)
  return Object.fromEntries([
    ...ITEM_SLOTS.map((s) => [s, value(s)]),
    ...FURNITURE_SLOTS.filter((s) => s in v).map((s) => [s, value(s)]),
  ]) as Equipped
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
      assetKey: null,
    })),
    ...COMPANIONS.map((c) => ({
      itemKey: companionKey(c.id),
      slot: 'COMPANION' as const,
      name: c.label,
      pricePoints: c.id === FREE_COMPANION ? 0 : COMPANION_PRICE,
      onSale: true,
      assetKey: null,
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

// ---------- 내 방 추억의 벽·추억 앨범 (API 명세 2.12, P27, FN-RET-09~11) ----------
/** 추억의 벽 슬롯 수(기준안 6, 확장안 3.1) */
export const FRAME_SLOT_COUNT = 6
const isoDate = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)
const text = (v: unknown) => (typeof v === 'string' ? v : '')
function memoryContractError(): never {
  throw new Error('추억 정보를 확인하지 못했어요. 다시 확인해 주세요.')
}
/** 회차 키(학생은 세션). 같은 테마도 주가 다르면 다른 회차 */
export const episodeKey = (e: { themeId: string; weekStart: string }) => `${e.themeId}@${e.weekStart}`

export interface FrameSlot {
  slotNo: number
  themeId: string
  weekStart: string
  title: string
  imageUrl: string | null
}
export function readFrameSlots(raw: unknown): FrameSlot[] {
  const slots = (raw as { slots?: unknown })?.slots
  if (!Array.isArray(slots)) return memoryContractError()
  const seen = new Set<number>()
  return slots.flatMap((x) => {
    const v = (x ?? {}) as Record<string, unknown>
    if (!Number.isInteger(v.slotNo) || Number(v.slotNo) < 1 || Number(v.slotNo) > FRAME_SLOT_COUNT ||
        typeof v.themeId !== 'string' || !v.themeId || !isoDate(v.weekStart)) return memoryContractError()
    if (seen.has(Number(v.slotNo))) return memoryContractError()
    seen.add(Number(v.slotNo))
    return [{ slotNo: Number(v.slotNo), themeId: v.themeId, weekStart: v.weekStart, title: text(v.title),
      imageUrl: typeof v.imageUrl === 'string' && v.imageUrl ? v.imageUrl : null }]
  }).sort((a, b) => a.slotNo - b.slotNo)
}

export interface AlbumItem {
  themeId: string
  weekStart: string
  title: string
  imageUrl: string | null
  awardedAt: string
  seen: boolean
  displayed: boolean
}
export interface Album { items: AlbumItem[]; page: number; size: number; totalElements: number }
export function readAlbum(raw: unknown): Album {
  const v = (raw ?? {}) as Record<string, unknown>
  if (!Array.isArray(v.items) || !nonNegativeInteger(v.page) || !nonNegativeInteger(v.size) || v.size < 1 ||
      !nonNegativeInteger(v.totalElements) || v.items.length > v.size) return memoryContractError()
  return {
    page: v.page, size: v.size, totalElements: v.totalElements,
    items: v.items.map((x) => {
      const i = (x ?? {}) as Record<string, unknown>
      if (typeof i.themeId !== 'string' || !i.themeId || !isoDate(i.weekStart) || typeof i.awardedAt !== 'string' ||
          !Number.isFinite(Date.parse(i.awardedAt)) || typeof i.seen !== 'boolean' || typeof i.displayed !== 'boolean')
        return memoryContractError()
      return { themeId: i.themeId, weekStart: i.weekStart, title: text(i.title),
        imageUrl: typeof i.imageUrl === 'string' && i.imageUrl ? i.imageUrl : null,
        awardedAt: i.awardedAt, seen: i.seen, displayed: i.displayed }
    }),
  }
}

export interface EpisodeMission {
  day: ThemeDay
  missionId: string
  title: string
  thinkingType: ThinkingType | null
  /** 기존 시도 상세(StudentWorkPage)로 여는 시도. 없으면 기록 없음 */
  attemptId: string | null
}
export interface Episode {
  themeId: string
  weekStart: string
  title: string
  awardedAt: string
  missions: EpisodeMission[]
  /** 엔딩을 보지 않았으면 outro·answer null(P23) */
  ending: { seen: boolean; outro: string | null; answer: string | null }
}
export function readEpisode(raw: unknown): Episode {
  const v = (raw ?? {}) as Record<string, unknown>
  const ending = (v.ending ?? {}) as Record<string, unknown>
  if (typeof v.themeId !== 'string' || !v.themeId || !isoDate(v.weekStart) || typeof v.awardedAt !== 'string' ||
      !Array.isArray(v.missions) || typeof ending.seen !== 'boolean') return memoryContractError()
  const seen = ending.seen
  return {
    themeId: v.themeId, weekStart: v.weekStart, title: text(v.title), awardedAt: v.awardedAt,
    missions: v.missions.flatMap((x) => {
      const m = (x ?? {}) as Record<string, unknown>
      if (!isDay(m.day) || typeof m.missionId !== 'string' || !m.missionId) return memoryContractError()
      return [{ day: m.day, missionId: m.missionId, title: text(m.title), thinkingType: isType(m.thinkingType) ? m.thinkingType : null,
        attemptId: typeof m.attemptId === 'string' && m.attemptId ? m.attemptId : null }]
    }).sort((a, b) => THEME_DAYS.indexOf(a.day) - THEME_DAYS.indexOf(b.day)),
    // 엔딩 전 값이 와도 보이지 않게 한 번 더 막는다(P23)
    ending: { seen, outro: seen && typeof ending.outro === 'string' ? ending.outro : null,
      answer: seen && typeof ending.answer === 'string' ? ending.answer : null },
  }
}
/** "11월 2주" 같은 회차 주 표시(KST 월요일 날짜 기준) */
export function weekLabel(weekStart: string) {
  const [, m, d] = weekStart.split('-').map(Number)
  return `${m}월 ${Math.floor((d - 1) / 7) + 1}주`
}

/** 착용 itemKey → 그림 assetKey(캐릭터 칸만). 목록을 못 받았거나 키가 없으면 그 칸은 비움(기본 모습) */
export function wornAssets(equipped: Equipped | undefined, items: LookItem[] | undefined): Partial<Record<'HAT' | 'OUTFIT' | 'ACCESSORY', string>> {
  const worn: Partial<Record<'HAT' | 'OUTFIT' | 'ACCESSORY', string>> = {}
  for (const slot of ['HAT', 'OUTFIT', 'ACCESSORY'] as const) {
    const key = equipped?.[slot]
    const asset = key ? items?.find((i) => i.itemKey === key && i.slot === slot)?.assetKey : null
    if (asset) worn[slot] = asset
  }
  return worn
}
