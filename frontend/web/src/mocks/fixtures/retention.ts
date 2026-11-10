import type { ThemeGrade } from '../../domain/admin/retention.ts'
import type { Child, Mission } from '../../domain/classroom.ts'
import {
  baseLookCatalog,
  companionKey,
  FREE_COMPANION,
  FREE_THEME,
  kstWeekday,
  POINT_RULES,
  REACTIONS,
  THEME_DAYS,
  themeKey,
} from '../../domain/retention.ts'
import type {
  ItemSlot,
  PointEvent,
  PointEventType,
  PostStatus,
  Reaction,
  ThemeDay,
} from '../../domain/retention.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import type { CompanionId } from '../../domain/studentLook.ts'

/**
 * 개발 목업 전용: 2026-11-06 결정(에픽 #396) 참여 기능의 가상 상태.
 * 실제 적립·해금·공개 판정은 core·learning 몫이고, 여기서는 화면 흐름을 확인할 만큼만 흉내 낸다.
 * 새로고침해도 유지되도록 sessionStorage에 가상 값만 둔다.
 */
const storageKey = 'sagomungchi:msw-retention:v1'
/** 요일을 바꿔 보려면 개발 도구에서 sessionStorage에 0(월)~6(일)을 넣는다. */
export const MOCK_WEEKDAY_KEY = 'sagomungchi:msw-weekday'

export interface MockPost {
  postId: string
  studentId: string
  nickname: string
  companion: CompanionId
  missionId: string
  missionTitle: string
  answer: string
  status: PostStatus
  createdAt: string
}
export interface MockLookItem {
  itemId: string
  code: string
  slot: ItemSlot
  name: string
  pricePoints: number
  assetKey: string
  status: 'ON_SALE' | 'STOPPED'
  updatedAt: string
}
export interface MockWeeklyTheme {
  themeId: string
  grade: ThemeGrade
  weekStart: string
  title: string
  intro: string
  days: { day: ThemeDay; missionId: string }[]
  status: 'DRAFT' | 'REVIEW_REQUIRED' | 'PUBLISHED' | 'UNPUBLISHED'
  updatedAt: string
}
interface State {
  ledger: Record<string, (PointEvent & { sourceKey: string })[]>
  unlocked: Record<string, string[]>
  unlockKeys: Record<string, string>
  unlockResults: Record<string, { itemKey: string; unlocked: true; balance: number }>
  community: Record<string, { enabled: boolean; updatedAt: string | null }>
  consent: Record<string, boolean>
  posts: MockPost[]
  /** postId → studentId → 반응 */
  reactions: Record<string, Record<string, Reaction[]>>
  reviewViews: string[]
  items: MockLookItem[]
  themes: MockWeeklyTheme[]
}

const now = () => new Date().toISOString()
const seedItems = (): MockLookItem[] => [
  { itemId: 'look-hat-1', code: 'HAT_ACORN', slot: 'HAT', name: '도토리 모자', pricePoints: 40, assetKey: 'looks/hat-acorn.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-outfit-1', code: 'OUTFIT_RAIN', slot: 'OUTFIT', name: '노란 비옷', pricePoints: 60, assetKey: 'looks/outfit-rain.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-acc-1', code: 'ACC_LENS', slot: 'ACCESSORY', name: '돋보기', pricePoints: 30, assetKey: 'looks/acc-lens.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-bg-1', code: 'BG_STARS', slot: 'BACKGROUND', name: '별빛 배경', pricePoints: 50, assetKey: 'looks/bg-stars.svg', status: 'ON_SALE', updatedAt: '2026-11-06T00:00:00Z' },
  { itemId: 'look-hat-2', code: 'HAT_CROWN', slot: 'HAT', name: '종이 왕관', pricePoints: 80, assetKey: 'looks/hat-crown.svg', status: 'STOPPED', updatedAt: '2026-11-06T00:00:00Z' },
]
const empty = (): State => ({
  ledger: {},
  unlocked: {},
  unlockKeys: {},
  unlockResults: {},
  community: {},
  consent: {},
  posts: [],
  reactions: {},
  reviewViews: [],
  items: seedItems(),
  themes: [],
})
export const retentionState: State = (() => {
  if (typeof sessionStorage === 'undefined') return empty()
  try {
    const raw = sessionStorage.getItem(storageKey)
    return raw ? { ...empty(), ...(JSON.parse(raw) as Partial<State>) } : empty()
  } catch {
    return empty()
  }
})()
export function persistRetention() {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(retentionState))
  } catch {
    /* 저장소를 못 쓰면 메모리 값만 유지 */
  }
}
export function resetRetention() {
  Object.assign(retentionState, empty())
  persistRetention()
}

export function mockWeekday() {
  try {
    const raw = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(MOCK_WEEKDAY_KEY)
    const n = raw === null ? NaN : Number(raw)
    if (Number.isInteger(n) && n >= 0 && n <= 6) return n
  } catch {
    /* 기본은 실제 요일 */
  }
  return kstWeekday()
}
/** 이번 주 월요일(KST) 날짜. */
export function weekStart(date = new Date()) {
  const kst = new Date(date.getTime() + 9 * 3600_000)
  kst.setUTCDate(kst.getUTCDate() - ((kst.getUTCDay() + 6) % 7))
  return kst.toISOString().slice(0, 10)
}

// ---------- 포인트 ----------
const rule = (type: Exclude<PointEventType, 'UNLOCK'>) => POINT_RULES.find((r) => r.type === type)!.amount
/** 처음 보는 학생은 해금을 시험할 수 있게 가상 적립 내역(합계 117)을 조금 둔다. */
function ledgerOf(studentId: string) {
  if (!retentionState.ledger[studentId]) {
    retentionState.ledger[studentId] = [
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-03T01:00:00Z', sourceKey: 'seed-1' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-04T01:00:00Z', sourceKey: 'seed-2' },
      { eventType: 'REVIEW_VIEWED', amount: 10, createdAt: '2026-11-01T01:00:00Z', sourceKey: 'seed-3' },
      { eventType: 'THEME_COMPLETED', amount: 30, createdAt: '2026-11-01T01:00:00Z', sourceKey: 'seed-4' },
      { eventType: 'COMMUNITY_POSTED', amount: 5, createdAt: '2026-11-04T01:10:00Z', sourceKey: 'seed-5' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-05T01:00:00Z', sourceKey: 'seed-6' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-06T01:00:00Z', sourceKey: 'seed-7' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-11-07T01:00:00Z', sourceKey: 'seed-8' },
      { eventType: 'REACTION_GIVEN', amount: 1, createdAt: '2026-11-07T02:00:00Z', sourceKey: 'seed-9' },
      { eventType: 'REACTION_GIVEN', amount: 1, createdAt: '2026-11-07T02:01:00Z', sourceKey: 'seed-10' },
      { eventType: 'MISSION_COMPLETED', amount: 10, createdAt: '2026-10-31T01:00:00Z', sourceKey: 'seed-11' },
      { eventType: 'REVIEW_VIEWED', amount: 10, createdAt: '2026-10-25T01:00:00Z', sourceKey: 'seed-12' },
    ]
  }
  return retentionState.ledger[studentId]
}
export const balanceOf = (studentId: string) => ledgerOf(studentId).reduce((sum, e) => sum + e.amount, 0)
export function pointsOf(studentId: string, page = 0, size = 20) {
  const items = [...ledgerOf(studentId)].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  return {
    balance: balanceOf(studentId),
    items: items.slice(page * size, page * size + size).map(({ eventType, amount, createdAt }) => ({ eventType, amount, createdAt })),
    page, size, totalElements: items.length,
  }
}
/** 같은 사건 키는 한 번만 적립(원장 UK `(student_id, event_type, source_key)` 흉내). */
export function earn(studentId: string, eventType: Exclude<PointEventType, 'UNLOCK'>, sourceKey: string) {
  const ledger = ledgerOf(studentId)
  if (ledger.some((e) => e.eventType === eventType && e.sourceKey === sourceKey)) return false
  if (eventType === 'REACTION_GIVEN') {
    const today = now().slice(0, 10)
    if (ledger.filter((e) => e.eventType === eventType && e.createdAt.startsWith(today)).length >= 5) return false
  }
  ledger.push({ eventType, amount: rule(eventType), createdAt: now(), sourceKey })
  return true
}

// ---------- 꾸미기 ----------
export const unlockedOf = (studentId: string) => (retentionState.unlocked[studentId] ??= [])
export function lookCatalog(studentId: string) {
  const owned = new Set(unlockedOf(studentId))
  return [
    ...baseLookCatalog().map((i) => ({
      ...i,
      unlocked: i.itemKey === themeKey(FREE_THEME) || i.itemKey === companionKey(FREE_COMPANION) || owned.has(i.itemKey),
    })),
    ...retentionState.items.map((i) => ({
      itemKey: i.code,
      slot: i.slot,
      name: i.name,
      pricePoints: i.pricePoints,
      unlocked: owned.has(i.code),
      onSale: i.status === 'ON_SALE',
      assetKey: i.assetKey,
    })),
  ].filter((i) => i.onSale || i.unlocked)
}
export function isUnlocked(studentId: string, itemKey: string) {
  return lookCatalog(studentId).some((i) => i.itemKey === itemKey && i.unlocked)
}

// ---------- 주간 테마 ----------
/** 게시된 관리자 테마가 있으면 그것을, 없으면 학생 미션으로 다섯 유형 하나씩 고른 가상 테마를 쓴다. */
export function themeMissions(missions: Mission[], grade: number) {
  const published = retentionState.themes.find((t) => t.status === 'PUBLISHED' && t.weekStart === weekStart() && t.grade === `G${Math.min(grade, 6)}`)
  if (published) {
    const byId = new Map(missions.map((m) => [m.id, m]))
    const days = published.days.flatMap((d) => (byId.get(d.missionId) ? [{ day: d.day, mission: byId.get(d.missionId)! }] : []))
    if (days.length === 5) return { themeId: published.themeId, title: published.title, intro: published.intro, reused: false, days }
  }
  const picked = THINKING_ORDER.map((type) => missions.find((m) => m.thinkingType === type)).filter((m): m is Mission => !!m)
  return {
    themeId: `mock-theme-${weekStart()}`,
    title: '이야기 마을의 수수께끼',
    intro: '이번 주에는 이야기 마을에서 일어난 일을 하루에 하나씩 살펴봐요. 금요일까지 다섯 가지 생각을 써 보면 마을의 수수께끼가 풀려요.',
    reused: picked.length < 5,
    days: picked.slice(0, 5).map((mission, i) => ({ day: THEME_DAYS[i], mission })),
  }
}
export function weeklyThemeFor(studentId: string, missions: Mission[], grade: number) {
  const weekday = mockWeekday()
  const theme = themeMissions(missions, grade)
  const weekend = weekday >= 5
  const days = theme.days.map(({ day, mission }, i) => ({
    day,
    missionId: mission.id,
    thinkingType: mission.thinkingType,
    title: mission.title,
    state: weekend || i < weekday ? 'CLOSED' : i === weekday ? 'OPEN' : 'LOCKED',
    attemptStatus: mission.status ?? 'NOT_STARTED',
  }))
  const viewed = retentionState.reviewViews.includes(`${studentId}:${weekStart()}`)
  return {
    themeId: theme.themeId,
    weekStart: weekStart(),
    title: theme.title,
    intro: weekday === 0 ? theme.intro : null,
    reused: theme.reused,
    days,
    review: {
      open: weekend,
      missions: days.map((d) => ({
        missionId: d.missionId,
        title: d.title,
        completed: d.attemptStatus === 'COMPLETED',
        missed: d.attemptStatus !== 'COMPLETED',
      })),
    },
    completed: viewed && days.length === 5 && days.every((d) => d.attemptStatus === 'COMPLETED'),
  }
}

// ---------- 커뮤니티 ----------
const friends: { nickname: string; companion: CompanionId; answer: (title: string) => string }[] = [
  { nickname: '하늘별', companion: 'tori', answer: (t) => `${t}에서 나는 먼저 무엇이 달라졌는지 찾았어. 왜냐하면 달라진 곳에 까닭이 숨어 있을 것 같았거든.` },
  { nickname: '초록콩', companion: 'kongi', answer: () => '나는 다른 방법도 생각해 봤어. 그래서 두 가지를 비교하니까 하나가 더 알맞아 보였어.' },
  { nickname: '구름빵', companion: 'monggeul', answer: () => '처음엔 잘 모르겠었는데 그림을 다시 보니 순서가 보였어. 그 순서대로 쓰면 이해가 돼.' },
]
export function seedFriendPosts(mission: Pick<Mission, 'id' | 'title'>) {
  if (retentionState.posts.some((p) => p.missionId === mission.id && p.studentId.startsWith('friend-'))) return
  friends.forEach((f, i) =>
    retentionState.posts.push({
      postId: `post-${mission.id}-friend-${i}`,
      studentId: `friend-${i}`,
      nickname: f.nickname,
      companion: f.companion,
      missionId: mission.id,
      missionTitle: mission.title,
      answer: f.answer(mission.title),
      status: 'VISIBLE',
      createdAt: `2026-11-0${4 + i}T03:00:00Z`,
    }),
  )
}
export const communityOf = (studentId: string) => (retentionState.community[studentId] ??= { enabled: false, updatedAt: null })
export const consentOf = (studentId: string) => retentionState.consent[studentId] ?? false
export function setConsent(studentId: string, agreed: boolean) {
  retentionState.consent[studentId] = agreed
  if (!agreed) setCommunityEnabled(studentId, false)
}
/** 끄면 공유물 HIDDEN_SETTING, 다시 켜면 HIDDEN_SETTING만 복원(신고 숨김은 유지, P20). */
export function setCommunityEnabled(studentId: string, enabled: boolean) {
  retentionState.community[studentId] = { enabled, updatedAt: now() }
  for (const p of retentionState.posts.filter((p) => p.studentId === studentId)) {
    if (!enabled && p.status === 'VISIBLE') p.status = 'HIDDEN_SETTING'
    if (enabled && p.status === 'HIDDEN_SETTING') p.status = 'VISIBLE'
  }
}
/** 마무리(학습 완료) 후 core가 하는 일: 미션당 최초 적립, 공개가 켜져 있으면 미션당 1개 공유. */
export function onMissionCompleted(student: Child, mission: Pick<Mission, 'id' | 'title'>, answer: string, companion: CompanionId) {
  earn(student.id, 'MISSION_COMPLETED', mission.id)
  if (!communityOf(student.id).enabled || !answer.trim()) return
  if (retentionState.posts.some((p) => p.studentId === student.id && p.missionId === mission.id)) return
  retentionState.posts.push({
    postId: `post-${mission.id}-${student.id}`,
    studentId: student.id,
    nickname: student.nickname,
    companion,
    missionId: mission.id,
    missionTitle: mission.title,
    answer,
    status: 'VISIBLE',
    createdAt: now(),
  })
  earn(student.id, 'COMMUNITY_POSTED', `${student.id}:${mission.id}`)
}
export function reactionCounts(postId: string) {
  const byStudent = retentionState.reactions[postId] ?? {}
  return Object.fromEntries(
    REACTIONS.map((r) => [r, Object.values(byStudent).filter((list) => list.includes(r)).length]),
  ) as Record<Reaction, number>
}
/** 같은 seed면 같은 순서가 되게 섞는다(정렬·순위 없음, P20). */
export function seededShuffle<T>(items: T[], seed: string) {
  let h = 2166136261
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619)
  const out = [...items]
  for (let i = out.length - 1; i > 0; i--) {
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0
    const j = h % (i + 1)
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}
