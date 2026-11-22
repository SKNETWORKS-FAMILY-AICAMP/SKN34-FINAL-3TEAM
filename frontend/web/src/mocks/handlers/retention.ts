import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import type { PlanChange } from '../../data/admin/themePlannerApi.ts'
import { mockPlannerDrafts } from './adminThemeDrafts.ts'
import { assignWeek, requireOpenWeek, weekLocked } from '../fixtures/themePlanning.ts'
import { http, HttpResponse } from 'msw/http'
import { ApiError } from '../../data/apiClient.ts'
import { baseLookCatalog, DECOR_MAX_OWNED, REACTIONS } from '../../domain/retention.ts'
import type { Reaction } from '../../domain/retention.ts'
import {
  balanceOf,
  communityOf,
  consentOf,
  decorOf,
  earn,
  frameSlotsOf,
  framesOf,
  isUnlocked,
  lookCatalog,
  MOCK_STORY,
  mockWeekday,
  persistRetention,
  pointsOf,
  reactionCounts,
  retentionState,
  seededShuffle,
  seedFriendPosts,
  setCommunityEnabled,
  setConsent,
  unlockedOf,
  weekRules,
  weekStart,
  weeklyThemeFor,
  frameImageOf,
  FRIEND_ROOMS,
  sharedAnswer,
} from '../fixtures/retention.ts'
import { guard, mockLatestAttempt, mockStudent, mockStudentHome, respond } from './student.ts'
import { mockThemeNone } from '../fixtures/themeState.ts'
import { fixtureStore } from '../fixtures/student.ts'
import { consentRows, docs, fixtureConsent, parentChild } from './parent.ts'
import { allow } from './admin.ts'
import { ALL_ITEM_SLOTS, DECOR_COLOR_RE, DECOR_SPOT_LIMIT, inDecorGrid, isDecorSurface, THEME_DAYS } from '../../domain/retention.ts'
import type { ItemSlot, ThemeDay } from '../../domain/retention.ts'
import type { MockLookItem, MockWeeklyTheme } from '../fixtures/retention.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import { missions as adminMissions } from '../fixtures/admin/operations.ts'
import type { ConsentDocument } from '../../domain/parent.ts'
import { mockPremium } from '../fixtures/payments.ts'

/** 이용권은 결제 목업 구독 한 곳에서 정한다(#602, Child.plan 없음). */
const planOf = (childId: string) => (mockPremium(childId) ? 'PREMIUM' : 'FREE') as 'FREE' | 'PREMIUM'

/**
 * 2026-11-06 결정(에픽 #396) 학생·학부모 참여 기능 목업. 계약은 API 명세 2.9~2.11(구현 예정).
 * core가 할 적립·해금·공개 판정을 화면 확인에 필요한 만큼만 흉내 낸다.
 */
const fail = (status: number, code: string, title: string): never => {
  throw new ApiError({ status, code, title })
}
/** 놓은 칸 응답(서버 정렬: 면 FLOOR → WALL_BACK → WALL_LEFT, 그다음 row·col) */
const SURFACE_ORDER = { FLOOR: 0, WALL_BACK: 1, WALL_LEFT: 2 } as const
function decorSpotsView(spots: { surface: 'FLOOR' | 'WALL_BACK' | 'WALL_LEFT'; col: number; row: number; itemKey: string; color?: string | null }[]) {
  return [...spots].sort((a, b) => SURFACE_ORDER[a.surface] - SURFACE_ORDER[b.surface] || a.row - b.row || a.col - b.col)
    .map((s) => { const item = retentionState.items.find((i) => i.code === s.itemKey); return { ...s, color: s.color ?? null, name: item?.name ?? '', assetKey: item?.assetKey ?? '' } })
}
const page = (request: Request) => {
  const q = new URL(request.url).searchParams
  return { page: Math.max(0, Number(q.get('page') ?? 0) || 0), size: Math.min(100, Math.max(1, Number(q.get('size') ?? 20) || 20)) }
}
const saved = <T>(value: T) => {
  persistRetention()
  return value
}
/**
 * 해금·방 소품 사기의 멱등 키 검사(core `IdempotencyService` 흉내). UUID가 아니면 400, 다른 요청(다른 경로나 다른 항목)에
 * 쓴 키면 422 `IDEMPOTENCY_KEY_REUSED`(API 명세 1장 오류 표). 처음 보는 키는 처리 전에 이 요청에 묶어서, 거절(4xx)된 키로
 * 다른 항목을 보내도 422다(core도 처리 전에 경로·요청 해시를 기록). 같은 요청 재전송은 처음 성공 응답이 있으면 그것을 쓴다.
 */
function idempotencyReceipt(request: Request, studentId: string, endpoint: 'unlock' | 'purchase', itemKey: string) {
  const key = request.headers.get('Idempotency-Key')
  if (!key || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(key))
    fail(400, 'VALIDATION_FAILED', 'Idempotency-Key(UUID)가 필요합니다.')
  const receipt = `${studentId}:${key}`
  const mine = endpoint === 'unlock' ? retentionState.unlockKeys : retentionState.purchaseKeys
  const other = endpoint === 'unlock' ? retentionState.purchaseKeys : retentionState.unlockKeys
  if (receipt in other || (receipt in mine && mine[receipt] !== itemKey))
    fail(422, 'IDEMPOTENCY_KEY_REUSED', '같은 키에 다른 요청을 사용할 수 없습니다.')
  mine[receipt] = itemKey
  return receipt
}
const isReaction = (v: unknown): v is Reaction => typeof v === 'string' && (REACTIONS as string[]).includes(v)
const postView = (p: (typeof retentionState.posts)[number]) => ({
  postId: p.postId,
  missionId: p.missionId,
  missionTitle: p.missionTitle,
  answer: sharedAnswer(p.answer),
  status: p.status,
  reactions: reactionCounts(p.postId),
  createdAt: p.createdAt,
})

export const retentionHandlers = [
  // ---------- 포인트·꾸미기 (2.10) ----------
  http.get('/api/v1/students/me/points', ({ request }) =>
    respond(async () => {
      guard(request)
      const { page: p, size } = page(request)
      return pointsOf(mockStudent().id, p, size)
    }),
  ),
  http.get('/api/v1/children/:childId/points', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      const { page: p, size } = page(request)
      return pointsOf(c.id, p, size)
    }),
  ),
  http.get('/api/v1/students/me/look-items', ({ request }) =>
    respond(async () => {
      guard(request)
      return { items: lookCatalog(mockStudent().id) }
    }),
  ),
  http.post('/api/v1/students/me/look-items/:itemKey/unlock', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const itemKey = decodeURIComponent(String(params.itemKey))
      const receipt = idempotencyReceipt(request, me.id, 'unlock', itemKey)
      const replay = retentionState.unlockResults[receipt]
      if (replay) return replay
      const item = lookCatalog(me.id).find((i) => i.itemKey === itemKey) ??
        // 판매 중단 아이템은 목록에서 빠지므로 관리자 목록으로 한 번 더 찾는다.
        retentionState.items.filter((i) => i.code === itemKey).map((i) => ({ itemKey: i.code, slot: i.slot, pricePoints: i.pricePoints, unlocked: false, onSale: false }))[0]
      if (!item) fail(404, 'LOOK_ITEM_NOT_FOUND', '없는 꾸미기 항목입니다.')
      // 방 소품은 해금이 아니라 사기(#704, core도 422 VALIDATION_FAILED)
      if (item!.slot === 'DECOR') fail(422, 'VALIDATION_FAILED', '방 소품은 사기로 살 수 있어요.')
      if (item!.unlocked || isUnlocked(me.id, itemKey)) {
        const result = { itemKey, unlocked: true as const, balance: balanceOf(me.id) }
        retentionState.unlockResults[receipt] = result
        return saved(result)
      }
      if (!item!.onSale) fail(409, 'LOOK_ITEM_NOT_ON_SALE', '지금은 해금할 수 없는 항목이에요.')
      if (balanceOf(me.id) < item!.pricePoints) fail(409, 'INSUFFICIENT_POINTS', '포인트가 모자라요.')
      retentionState.ledger[me.id].push({ eventType: 'UNLOCK', amount: -item!.pricePoints, createdAt: new Date().toISOString(), sourceKey: receipt })
      unlockedOf(me.id).push(itemKey)
      const result = { itemKey, unlocked: true as const, balance: balanceOf(me.id) }
      retentionState.unlockResults[receipt] = result
      return saved(result)
    }),
  ),
  // 방 소품 사기(#704): 같은 아이템을 여러 번 산다. 키가 다르면 새 구매, 같은 키는 처음 응답(한 번만 차감)
  http.post('/api/v1/students/me/look-items/:itemKey/purchase', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const itemKey = decodeURIComponent(String(params.itemKey))
      const receipt = idempotencyReceipt(request, me.id, 'purchase', itemKey)
      const replay = retentionState.purchaseResults[receipt]
      if (replay) return replay
      // 테마·캐릭터·착용 아이템·가구·바닥은 사기 대상이 아니다(core 422 VALIDATION_FAILED, 없는 항목만 404)
      if (baseLookCatalog().some((i) => i.itemKey === itemKey)) fail(422, 'VALIDATION_FAILED', '방 소품만 여러 개 살 수 있어요.')
      const item = retentionState.items.find((i) => i.code === itemKey)
      if (!item) fail(404, 'LOOK_ITEM_NOT_FOUND', '없는 꾸미기 항목입니다.')
      if (item!.slot !== 'DECOR') fail(422, 'VALIDATION_FAILED', '방 소품만 여러 개 살 수 있어요.')
      if (item!.status !== 'ON_SALE') fail(409, 'LOOK_ITEM_NOT_ON_SALE', '지금은 살 수 없는 항목이에요.')
      const owned = decorOf(me.id)[itemKey] ?? 0
      if (owned >= DECOR_MAX_OWNED) fail(409, 'LOOK_DECOR_LIMIT', `이 방 소품은 ${DECOR_MAX_OWNED}개까지 가질 수 있어요.`)
      if (balanceOf(me.id) < item!.pricePoints) fail(409, 'INSUFFICIENT_POINTS', '포인트가 모자라요.')
      // 원장 사건 키는 core처럼 구매마다 다르게(itemKey:Idempotency-Key)
      retentionState.ledger[me.id].push({ eventType: 'UNLOCK', amount: -item!.pricePoints, createdAt: new Date().toISOString(), sourceKey: `${itemKey}:${receipt}` })
      decorOf(me.id)[itemKey] = owned + 1
      const result = { itemKey, ownedCount: owned + 1, balance: balanceOf(me.id) }
      retentionState.purchaseResults[receipt] = result
      return saved(result)
    }),
  ),

  // ---------- 주간 테마·되돌아보기 (2.11) ----------
  http.get('/api/v1/students/me/weekly-theme', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      if (mockThemeNone()) return {} // 개발 목업 "테마 없음"(빈 응답이면 웹은 테마 없는 홈)
      const week = weeklyThemeFor(me.id, (await mockStudentHome(me)).missions, me.grade, planOf(me.id))
      // core가 조회 응답으로 하는 테마 적립 보충을 흉내 낸다(#485): 당일 풀이·개근·주간 완주.
      const key = `${me.id}:${weekStart()}`
      week.days.forEach((d) => d.completedOnDay && earn(me.id, 'THEME_ON_TIME', `${key}:${d.day}`))
      if (week.completed) earn(me.id, 'THEME_COMPLETED', key)
      if (week.finished) earn(me.id, 'THEME_FINISHED', key)
      return saved(week)
    }),
  ),
  http.post('/api/v1/students/me/weekly-theme/review-views', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      // 토요일(프리미엄은 일요일도)만. 평일·무료 일요일은 409(#484).
      if (!weekRules(mockWeekday(), planOf(me.id)).weekend) fail(409, 'THEME_REVIEW_NOT_ALLOWED', '되돌아보기는 토요일에 열려요.')
      const key = `${me.id}:${weekStart()}`
      const first = !retentionState.reviewViews.includes(key)
      if (first) retentionState.reviewViews.push(key)
      earn(me.id, 'REVIEW_VIEWED', key)
      const week = weeklyThemeFor(me.id, (await mockStudentHome(me)).missions, me.grade, planOf(me.id))
      if (week.completed) earn(me.id, 'THEME_COMPLETED', key)
      return saved({ firstViewThisWeek: first, completed: week.completed })
    }),
  ),
  // 시작·종료 이야기 열람(learning #438·#484 판정 흉내): INTRO는 무료 일요일만 거부, OUTRO는 엔딩 뒤에만.
  http.post('/api/v1/students/me/weekly-theme/story-views', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const { kind } = ((await request.json().catch(() => ({}))) ?? {}) as { kind?: unknown }
      if (kind !== 'INTRO' && kind !== 'OUTRO') fail(400, 'VALIDATION_FAILED', '이야기 종류를 확인해 주세요.')
      const week = weeklyThemeFor(me.id, (await mockStudentHome(me)).missions, me.grade, planOf(me.id))
      if (weekRules(mockWeekday(), planOf(me.id)).closed || (kind === 'OUTRO' && week.ending !== 'ENDED'))
        fail(409, 'THEME_STORY_NOT_ALLOWED', '지금은 이 이야기를 기록할 수 없어요.')
      const key = `${me.id}:${weekStart()}:${kind}`
      const first = !retentionState.storyViews.includes(key)
      if (first) retentionState.storyViews.push(key)
      return saved({ kind, firstViewThisWeek: first })
    }),
  ),
  // 큰 질문 정답 고르기(learning #484 판정 흉내): 금요일 문제 학습 완료 뒤 한 주 한 번, 후보 밖은 400.
  http.post('/api/v1/students/me/weekly-theme/answer-picks', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const { pick } = ((await request.json().catch(() => ({}))) ?? {}) as { pick?: unknown }
      if (typeof pick !== 'string' || !pick.trim()) fail(400, 'VALIDATION_FAILED', '고를 후보를 확인해 주세요.')
      const missions = (await mockStudentHome(me)).missions
      const week = weeklyThemeFor(me.id, missions, me.grade, planOf(me.id))
      const key = `${me.id}:${weekStart()}`
      if (!week.candidates?.includes(pick as string)) fail(400, 'VALIDATION_FAILED', '후보 중에서 골라 주세요.')
      if (weekRules(mockWeekday(), planOf(me.id)).closed || week.days[4]?.attemptStatus !== 'COMPLETED' || retentionState.picks[key])
        fail(409, 'THEME_PICK_NOT_ALLOWED', '지금은 정답을 고를 수 없어요.')
      retentionState.picks[key] = { pick: pick as string, correct: pick === MOCK_STORY.answer, at: new Date().toISOString() }
      const after = weeklyThemeFor(me.id, missions, me.grade, planOf(me.id))
      return saved({ correct: pick === MOCK_STORY.answer, ending: after.ending, answer: after.answer })
    }),
  ),

  // ---------- 내 방 추억의 벽·추억 앨범 (2.12 기준안, P27) ----------
  http.get('/api/v1/students/me/room/frame-slots', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const frames = framesOf(me.id, (await mockStudentHome(me)).missions)
      return { slots: frameSlotsOf(me.id).flatMap((s) => {
        const f = frames.find((x) => x.themeId === s.themeId && x.weekStart === s.weekStart)
        return f ? [{ ...s, title: f.title, imageUrl: frameImageOf(f) }] : []
      }) }
    }),
  ),
  // 방 소품 놓은 칸(#705, core #723 계약안): 서버처럼 범위·같은 기준 칸·개수 상한·보유 개수만 검사(가구 칸·겹침·길은 웹)
  http.get('/api/v1/students/me/room/decor-spots', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      return { spots: decorSpotsView((retentionState.decorSpots ??= {})[me.id] ?? []) }
    }),
  ),
  http.put('/api/v1/students/me/room/decor-spots', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const body = (await request.json()) as { spots?: unknown }
      const bad = () => fail(422, 'VALIDATION_FAILED', '자리 번호와 방 소품을 확인해 주세요. 가진 개수만큼만 놓을 수 있어요.')
      if (!Array.isArray(body.spots) || body.spots.length > DECOR_SPOT_LIMIT) bad()
      const spots = (body.spots as Record<string, unknown>[]).map((s) => ({ surface: s?.surface, col: Number(s?.col), row: Number(s?.row), itemKey: String(s?.itemKey ?? ''), color: s?.color ?? null }))
      if (spots.some((s) => !isDecorSurface(s.surface) || !inDecorGrid(s.surface, s.col, s.row) || !s.itemKey || (s.color !== null && (typeof s.color !== 'string' || !DECOR_COLOR_RE.test(s.color))))) bad()
      if (new Set(spots.map((s) => `${s.surface}:${s.col}:${s.row}`)).size !== spots.length) bad()
      const owned = decorOf(me.id)
      const count: Record<string, number> = {}
      for (const s of spots) count[s.itemKey] = (count[s.itemKey] ?? 0) + 1
      if (Object.entries(count).some(([code, n]) => (owned[code] ?? 0) < n)) bad()
      ;(retentionState.decorSpots ??= {})[me.id] = spots as { surface: 'FLOOR' | 'WALL_BACK' | 'WALL_LEFT'; col: number; row: number; itemKey: string; color: string | null }[]
      return saved({ spots: decorSpotsView(retentionState.decorSpots[me.id]) })
    }),
  ),
  http.put('/api/v1/students/me/room/frame-slots', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const frames = framesOf(me.id, (await mockStudentHome(me)).missions)
      const body = (await request.json()) as { slots?: unknown }
      if (!Array.isArray(body.slots)) fail(422, 'VALIDATION_FAILED', '슬롯 목록을 확인해 주세요.')
      const slots = (body.slots as Record<string, unknown>[]).map((s) => ({ slotNo: Number(s?.slotNo), themeId: String(s?.themeId ?? ''), weekStart: String(s?.weekStart ?? '') }))
      const keys = new Set(slots.map((s) => `${s.themeId}@${s.weekStart}`))
      if (slots.some((s) => !Number.isInteger(s.slotNo) || s.slotNo < 1 || s.slotNo > 6) ||
          new Set(slots.map((s) => s.slotNo)).size !== slots.length || keys.size !== slots.length)
        fail(422, 'VALIDATION_FAILED', '슬롯 번호나 액자가 겹쳐요.')
      if (slots.some((s) => !frames.some((f) => f.themeId === s.themeId && f.weekStart === s.weekStart)))
        fail(404, 'THEME_FRAME_NOT_FOUND', '가지고 있지 않은 액자예요.')
      retentionState.frameSlots[me.id] = slots
      return saved({ slots: slots.map((s) => ({ ...s, title: frames.find((f) => f.themeId === s.themeId && f.weekStart === s.weekStart)!.title,
        imageUrl: frameImageOf(frames.find((f) => f.themeId === s.themeId && f.weekStart === s.weekStart)!) })) })
    }),
  ),
  http.get('/api/v1/students/me/album', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const { page: p, size } = page(request)
      const frames = [...framesOf(me.id, (await mockStudentHome(me)).missions)].sort((a, b) => b.weekStart.localeCompare(a.weekStart))
      const shown = new Set(frameSlotsOf(me.id).map((s) => `${s.themeId}@${s.weekStart}`))
      return {
        items: frames.slice(p * size, p * size + size).map((f) => ({ themeId: f.themeId, weekStart: f.weekStart, title: f.title, imageUrl: frameImageOf(f),
          awardedAt: f.awardedAt, seen: !!f.seenAt, displayed: shown.has(`${f.themeId}@${f.weekStart}`) })),
        page: p, size, totalElements: frames.length,
      }
    }),
  ),
  http.get('/api/v1/students/me/album/:themeId/:weekStart', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const f = framesOf(me.id, (await mockStudentHome(me)).missions)
        .find((x) => x.themeId === String(params.themeId) && x.weekStart === String(params.weekStart))
      if (!f) return fail(404, 'THEME_FRAME_NOT_FOUND', '가지고 있지 않은 액자예요.')
      return {
        themeId: f.themeId, weekStart: f.weekStart, title: f.title, imageUrl: frameImageOf(f), awardedAt: f.awardedAt,
        missions: f.missions.map((m) => ({ ...m, attemptId: mockLatestAttempt(me.id, m.missionId) })),
        ending: { seen: f.endingSeen, outro: f.endingSeen ? f.outro : null, answer: f.endingSeen ? f.answer : null },
      }
    }),
  ),
  http.post('/api/v1/students/me/album/:themeId/:weekStart/seen', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const f = framesOf(me.id, (await mockStudentHome(me)).missions)
        .find((x) => x.themeId === String(params.themeId) && x.weekStart === String(params.weekStart))
      if (!f) return fail(404, 'THEME_FRAME_NOT_FOUND', '가지고 있지 않은 액자예요.')
      f.seenAt ??= new Date().toISOString()
      persistRetention()
      return undefined // 204 본문 없음
    }, 204),
  ),

  // ---------- 커뮤니티 (2.9) ----------
  http.get('/api/v1/students/me/community-settings', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      return { ...communityOf(me.id), consentGranted: consentOf(me.id) }
    }),
  ),
  http.put('/api/v1/students/me/community-settings', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const { enabled } = (await request.json()) as { enabled?: unknown }
      if (typeof enabled !== 'boolean') fail(422, 'VALIDATION_FAILED', '공개 여부를 골라 주세요.')
      if (enabled && !consentOf(me.id)) fail(409, 'COMMUNITY_CONSENT_REQUIRED', '학부모님의 커뮤니티 동의가 먼저 필요해요.')
      setCommunityEnabled(me.id, enabled as boolean)
      return saved({ ...communityOf(me.id), consentGranted: consentOf(me.id) })
    }),
  ),
  http.get('/api/v1/missions/:missionId/community-posts', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const mission = (await mockStudentHome(me)).missions.find((m) => m.id === String(params.missionId))
      if (!mission) fail(404, 'MISSION_NOT_FOUND', '미션을 찾을 수 없어요.')
      if (mission!.status !== 'COMPLETED') fail(403, 'COMMUNITY_LOCKED', '이 미션을 마무리하면 친구들 생각을 볼 수 있어요.')
      seedFriendPosts(mission!)
      const seed = new URL(request.url).searchParams.get('seed') ?? ''
      const visible = retentionState.posts.filter((p) => p.missionId === mission!.id && p.status === 'VISIBLE' && p.studentId !== me.id)
      const { page: p, size } = page(request)
      return saved({
        items: seededShuffle(visible, seed)
          .slice(p * size, p * size + size)
          .map((x) => ({
            postId: x.postId,
            author: { nickname: x.nickname, look: { theme: 'lake', companion: x.companion, equipped: { HAT: x.equipped?.HAT ?? null, OUTFIT: x.equipped?.OUTFIT ?? null, ACCESSORY: x.equipped?.ACCESSORY ?? null, BACKGROUND: null } } },
            answer: sharedAnswer(x.answer),
            myReactions: retentionState.reactions[x.postId]?.[me.id] ?? [],
            createdAt: x.createdAt,
          })),
      })
    }),
  ),
  // 친구 방 구경(#708 계약, #709): 친구 생각 목록과 같은 조건. 학생 ID·회차 키는 내보내지 않는다
  http.get('/api/v1/community-posts/:postId/room', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const post = retentionState.posts.find((p) => p.postId === String(params.postId))
      if (!post || post.status !== 'VISIBLE') fail(404, 'COMMUNITY_POST_NOT_FOUND', '볼 수 없는 글이에요.')
      if (post!.studentId === me.id) fail(409, 'COMMUNITY_OWN_POST', '내 글이에요.')
      const mission = (await mockStudentHome(me)).missions.find((m) => m.id === post!.missionId)
      if (mission && mission.status !== 'COMPLETED') fail(403, 'COMMUNITY_LOCKED', '이 미션을 마무리하면 친구들 생각을 볼 수 있어요.')
      const room = FRIEND_ROOMS[Number(post!.studentId.replace('friend-', ''))]
      if (!room) fail(404, 'COMMUNITY_POST_NOT_FOUND', '볼 수 없는 글이에요.')
      const asset = (code: string | undefined) => (code ? retentionState.items.find((i) => i.code === code)?.assetKey ?? null : null)
      return {
        nickname: post!.nickname,
        look: { theme: 'lake', companion: post!.companion,
          equipped: { HAT: asset(post!.equipped?.HAT), OUTFIT: asset(post!.equipped?.OUTFIT), ACCESSORY: asset(post!.equipped?.ACCESSORY) } },
        room: { wallpaper: room!.wallpaper, floor: room!.floor, furniture: room!.furniture, decor: room!.decor ?? [],
          frames: room!.frames.map((f, i) => ({ slotNo: i + 1, title: f.title, imageUrl: f.withImage ? frameImageOf(f) : null })) },
      }
    }),
  ),
  http.get('/api/v1/students/me/community-posts', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      return { items: retentionState.posts.filter((p) => p.studentId === me.id).map(postView) }
    }),
  ),
  http.get('/api/v1/children/:childId/community-posts', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      return { items: retentionState.posts.filter((p) => p.studentId === c.id).map(postView) }
    }),
  ),
  ...(['put', 'delete'] as const).map((method) =>
    http[method]('/api/v1/community-posts/:postId/reactions/:reaction', ({ request, params }) =>
      respond(async () => {
        guard(request)
        const me = mockStudent()
        const reaction = String(params.reaction)
        if (!isReaction(reaction)) fail(422, 'VALIDATION_FAILED', '고를 수 없는 반응이에요.')
        const post = retentionState.posts.find((p) => p.postId === String(params.postId))
        if (!post || post.status !== 'VISIBLE') fail(404, 'COMMUNITY_POST_NOT_FOUND', '볼 수 없는 글이에요.')
        if (post!.studentId === me.id) fail(409, 'COMMUNITY_OWN_POST', '내 글에는 반응할 수 없어요.')
        const mission = (await mockStudentHome(me)).missions.find((m) => m.id === post!.missionId)
        if (mission?.status !== 'COMPLETED') fail(403, 'COMMUNITY_LOCKED', '이 미션을 마무리하면 반응할 수 있어요.')
        const mine = ((retentionState.reactions[post!.postId] ??= {})[me.id] ??= [])
        const had = mine.includes(reaction as Reaction)
        if (method === 'put' && !had) {
          mine.push(reaction as Reaction)
          earn(me.id, 'REACTION_GIVEN', `${post!.postId}:${reaction}`)
        }
        if (method === 'delete' && had) mine.splice(mine.indexOf(reaction as Reaction), 1)
        persistRetention()
        return new HttpResponse(null, { status: 204 })
      }),
    ),
  ),
  // 커뮤니티 신고만 여기서 받는다. 다른 신고 대상은 기존 지원 목업으로 넘긴다.
  http.post('/api/v1/error-reports', async ({ request }) => {
    const body = (await request.clone().json().catch(() => null)) as { targetType?: string; targetId?: string; category?: string; comment?: string } | null
    if (body?.targetType !== 'COMMUNITY_POST') return undefined
    return respond(async () => {
      guard(request)
      const reporter = mockStudent()
      const key = request.headers.get('Idempotency-Key')
      const category = body.category ?? ''
      const comment = body.comment ?? ''
      if (!key || !['WRONG_JUDGMENT', 'ODD_QUESTION', 'MISMATCH', 'INAPPROPRIATE', 'OTHER'].includes(category) || comment.length > 10000)
        fail(400, 'VALIDATION_FAILED', '신고 내용을 확인해 주세요.')
      const replay = retentionState.communityReports.find((item) => item.reporterId === reporter.id && item.key === key)
      if (replay) {
        if (replay.report.targetId !== body.targetId || replay.report.category !== category || replay.report.comment !== comment)
          fail(409, 'SUPPORT_STATE_CONFLICT', '같은 접수 번호의 신고 내용이 다릅니다.')
        return { ...replay.report, status: 'RECEIVED', reviewReason: null, reviewResult: null }
      }
      const post = retentionState.posts.find((p) => p.postId === body.targetId)
      if (!post || !['VISIBLE', 'HIDDEN_REPORT'].includes(post.status)) fail(404, 'COMMUNITY_POST_NOT_FOUND', '볼 수 없는 글이에요.')
      if (post!.studentId === reporter.id) fail(409, 'COMMUNITY_OWN_POST', '내 공유물은 신고할 수 없어요.')
      const report = {
        reportId: crypto.randomUUID(),
        status: 'RECEIVED' as const,
        targetType: 'COMMUNITY_POST',
        targetId: post!.postId,
        category,
        comment,
        corrections: [],
      }
      post!.status = 'HIDDEN_REPORT'
      retentionState.communityReports.unshift({ reporterId: reporter.id, key: key!, report })
      return saved(report)
    }, 201)
  }),
  // 현재 동의 문서에 선택 문서 COMMUNITY를 더한다(가입 화면은 이용 안내·개인정보만 고른다).
  http.get('/api/v1/consent-documents', () =>
    HttpResponse.json({ items: [...docs, COMMUNITY_DOCUMENT], page: 0, size: docs.length + 1, totalElements: docs.length + 1 }),
  ),
  // 학부모 COMMUNITY 선택 동의(2.9): 자녀 단위로 이 문서 하나만 보내는 요청을 여기서 받는다.
  http.post('/api/v1/me/consents', async ({ request }) => {
    const body = (await request.clone().json().catch(() => null)) as
      | { childId?: string; consents?: { documentId?: string; version?: string; agreed?: boolean }[] }
      | null
    const only = body?.consents?.length === 1 ? body.consents[0] : null
    if (!body?.childId || only?.documentId !== COMMUNITY_DOCUMENT.documentId) return undefined
    return respond(async () => {
      const c = await parentChild(request, body.childId!)
      if (only.version !== COMMUNITY_DOCUMENT.version) fail(409, 'CONSENT_DOCUMENT_CHANGED', '현재 문서를 다시 확인해 주세요.')
      const entry = fixtureConsent(COMMUNITY_DOCUMENT, c.id, only.agreed === true)
      if (!entry.agreed) entry.status = 'WITHDRAWN'
      ;(await consentRows()).unshift(entry)
      setConsent(c.id, entry.agreed)
      return saved({ items: [entry], page: 0, size: 1, totalElements: 1 })
    })
  }),
  // 철회는 기존 목업이 처리하고, COMMUNITY면 공개 설정도 함께 끈다(P09 선택 동의).
  http.post('/api/v1/me/consents/:consentId/withdrawal', async ({ params }) => {
    const entry = (await consentRows()).find((c) => c.consentId === params.consentId)
    if (entry?.document.kind === 'COMMUNITY' && entry.studentId) {
      setConsent(entry.studentId, false)
      persistRetention()
    }
    return undefined
  }),

  // ---------- 관리자 주간 테마·꾸미기 아이템 (2.8, CONTENT) ----------
  http.get('/api/v1/admin/weekly-themes/planner', ({request})=>respond(async()=>{
    allow(request,'CONTENT')
    const query=new URL(request.url).searchParams
    const grade=query.get('grade')??'', start=query.get('weekStart')??''
    if(!(grade in THEME_GRADE_LABELS)||!isPlanMonday(start)) fail(400,'VALIDATION_FAILED','학년 및 월요일을 확인해 주세요.')
    const candidates=mockPlannerDrafts().filter(d=>d.grade===grade)
    const weeks=Array.from({length:4},(_,index)=>{
      const date=new Date(start+'T00:00:00Z')
      date.setUTCDate(date.getUTCDate()+7*index)
      const week=date.toISOString().slice(0,10)
      return {weekStart:week,locked:weekLocked(grade,week),planned:candidates.find(d=>d.plannedWeek===week)??null,
        themes:retentionState.themes.filter(t=>t.grade===grade&&t.weekStart===week).map(t=>({themeId:t.themeId,title:t.title,status:t.status,version:t.version??1}))}
    })
    return {grade,weekStart:start,weeks,candidates}
  })),
  http.put('/api/v1/admin/weekly-themes/planner',({request})=>respond(async()=>{
    allow(request,'CONTENT')
    const plan=await request.json() as PlanChange
    const candidates=mockPlannerDrafts()
    const draft=candidates.find(d=>d.draftId===plan.draftId && d.grade===plan.grade)
    if(!draft||draft.plannedWeek!==plan.expectedWeek) fail(409,'PLAN_CONFLICT','초안 편성 주를 새로 확인해 주세요.')
    if(plan.targetWeek!==null && (!isPlanMonday(plan.targetWeek)||plan.targetWeek<weekStart())) fail(400,'VALIDATION_FAILED','편성 주는 이번 주 이후 월요일입니다.')
    if(plan.expectedWeek) requireOpenWeek(plan.grade,plan.expectedWeek)
    if(plan.targetWeek) requireOpenWeek(plan.grade,plan.targetWeek)
    const other=plan.targetWeek && candidates.find(d=>d.grade===plan.grade&& d.draftId!==plan.draftId&&d.plannedWeek===plan.targetWeek)
    const displaced=other?other.draftId:null
    if(displaced!==plan.expectedTargetDraftId) fail(409,'PLAN_CONFLICT','대상 주의 후보가 바뀌었습니다.')
    if(displaced) assignWeek(displaced,plan.expectedWeek)
    assignWeek(plan.draftId,plan.targetWeek)
    return {draftId:plan.draftId, grade:plan.grade, plannedWeek:plan.targetWeek, displacedDraftId:displaced}
  })),
  http.get('/api/v1/admin/weekly-themes', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const q = new URL(request.url).searchParams
      const items = retentionState.themes.filter(
        (t) =>
          (!q.get('grade') || t.grade === q.get('grade')) &&
          (!q.get('status') || t.status === q.get('status')) &&
          (q.get('status') !== 'REVIEW_REQUIRED' || !weekLocked(t.grade,t.weekStart)) &&
          (!q.get('weekStart') || t.weekStart === q.get('weekStart')),
      )
      const page=Number(q.get('page')??0), size=Number(q.get('size')??20)
      return { items:items.slice(page*size,(page+1)*size), page, size, totalElements: items.length }
    }),
  ),
  http.post('/api/v1/admin/weekly-themes', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const t: MockWeeklyTheme = {
        ...themeInput(await request.json()),
        themeId: `theme-${crypto.randomUUID().slice(0, 8)}`,
        status: 'DRAFT',
        updatedAt: new Date().toISOString(),
      }
      requireOpenWeek(t.grade,t.weekStart)
      retentionState.themes.unshift(t)
      return saved(t)
    }, 201),
  ),
  http.get('/api/v1/admin/weekly-themes/:themeId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const theme=themeById(String(params.themeId))
      return {...theme,version:theme.version??1,weekLocked:weekLocked(theme.grade,theme.weekStart)}
    }),
  ),
  http.put('/api/v1/admin/weekly-themes/:themeId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const t = themeById(String(params.themeId))
      const input=themeInput(await request.json())
      requireOpenWeek(t.grade,t.weekStart)
      requireOpenWeek(input.grade,input.weekStart)
      Object.assign(t, input, {status:'DRAFT',version:(t.version??1)+1,updatedAt:new Date().toISOString()})
      return saved(t)
    }),
  ),
  ...(['review-request', 'publish', 'unpublish'] as const).map((action) =>
    http.post(`/api/v1/admin/weekly-themes/:themeId/${action}`, ({ request, params }) =>
      respond(async () => {
        allow(request, 'CONTENT')
        const t = themeById(String(params.themeId))
        requireOpenWeek(t.grade,t.weekStart)
        if (action === 'review-request') {
          if (t.status !== 'DRAFT' && t.status !== 'UNPUBLISHED') fail(409, 'INVALID_STATE', '검토를 요청할 수 없습니다.')
          t.status = 'REVIEW_REQUIRED'
        } else if (action === 'publish') {
          const body=await request.json() as {expectedVersion?:number;expectedPlannedDraftId?:string|null}
          if(body.expectedVersion!==undefined && body.expectedVersion!==(t.version??1)) fail(409,'PLAN_CONFLICT','테마 버전이 바뀌었습니다.')
          if (t.status !== 'REVIEW_REQUIRED') fail(409, 'INVALID_STATE', '검토 요청한 테마만 게시할 수 있습니다.')
          const errors = await publishErrors(t)
          if (errors.length)
            throw new ApiError({
              status: 422,
              code: 'WEEKLY_THEME_PUBLISH_INCOMPLETE',
              title: '게시 검사를 통과하지 못했습니다.',
              errors: errors.map((message) => ({ message })),
            } as never)
          requireOpenWeek(t.grade,t.weekStart)
          const planned=mockPlannerDrafts().find(d=>d.grade===t.grade&&d.plannedWeek===t.weekStart)
          if('expectedPlannedDraftId' in body && body.expectedPlannedDraftId!==(planned?.draftId??null)) fail(409,'PLAN_CONFLICT','해제할 편성 후보가 바뀌었습니다.')
          const catalog=fixtureStore.snapshot().catalog ?? []
          t.missionSnapshots=t.days.map(day=>catalog.find(m=>m.id===day.missionId)
            ?? fail(422,'WEEKLY_THEME_PUBLISH_INCOMPLETE','게시 버전의 미션 내용을 찾지 못했습니다.'))
          t.status = 'PUBLISHED'
          mockPlannerDrafts().filter(d=>d.grade===t.grade && d.plannedWeek===t.weekStart).forEach(d=>assignWeek(d.draftId,null))
        } else {
          fail(409,'INVALID_STATE','게시 중단할 수 없습니다.')
        }
        t.updatedAt = new Date().toISOString()
        return saved(t)
      }),
    ),
  ),
  http.get('/api/v1/admin/look-items', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const params = new URL(request.url).searchParams
      const slot = params.get('slot')
      if (slot && !(ALL_ITEM_SLOTS as string[]).includes(slot)) fail(422, 'VALIDATION_FAILED', '칸을 확인해 주세요.')
      const page = Number(params.get('page') ?? 0), size = Number(params.get('size') ?? 20)
      if (!Number.isSafeInteger(page) || page < 0 || !Number.isSafeInteger(size) || size < 1 || size > 100)
        fail(400, 'VALIDATION_FAILED', '페이지와 크기를 확인해 주세요.')
      const items = retentionState.items.filter((i) => !slot || i.slot === slot)
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.itemId.localeCompare(b.itemId))
      return { items: items.slice(page * size, (page + 1) * size), page, size, totalElements: items.length }
    }),
  ),
  http.post('/api/v1/admin/look-items', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const b = (await request.json()) as Partial<MockLookItem>
      if (typeof b.code !== 'string' || !/^[A-Z0-9_]{3,40}$/.test(b.code)) fail(422, 'VALIDATION_FAILED', '코드를 확인해 주세요.')
      if (retentionState.items.some((i) => i.code === b.code)) fail(409, 'LOOK_ITEM_CODE_DUPLICATE', '이미 있는 코드입니다.')
      if (!(ALL_ITEM_SLOTS as string[]).includes(String(b.slot))) fail(422, 'VALIDATION_FAILED', '칸을 확인해 주세요.')
      const item: MockLookItem = {
        itemId: `look-${crypto.randomUUID().slice(0, 8)}`,
        code: b.code!,
        slot: b.slot as ItemSlot,
        ...itemFields(b),
        status: 'ON_SALE',
        // 학생 목록 createdAt(#704 "새로 나왔어요")의 기준
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
      retentionState.items.push(item)
      return saved(item)
    }, 201),
  ),
  http.patch('/api/v1/admin/look-items/:itemId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const item = retentionState.items.find((i) => i.itemId === String(params.itemId))
      if (!item) fail(404, 'NOT_FOUND', '아이템을 찾을 수 없습니다.')
      const b = (await request.json()) as Partial<MockLookItem>
      if (b.status !== undefined && b.status !== 'ON_SALE' && b.status !== 'STOPPED') fail(422, 'VALIDATION_FAILED', '상태를 확인해 주세요.')
      const edits = b.name !== undefined || b.pricePoints !== undefined || b.assetKey !== undefined
      Object.assign(item!, edits ? itemFields({ ...item, ...b }) : {}, b.status ? { status: b.status } : {}, { updatedAt: new Date().toISOString() })
      return saved(item)
    }),
  ),
]

export const COMMUNITY_DOCUMENT: ConsentDocument = {
  documentId: 'community-v1',
  kind: 'COMMUNITY',
  version: '1.0',
  title: '풀이 공유 커뮤니티 이용 동의(선택)',
  content:
    '자녀가 마무리한 미션 답을 같은 미션을 마무리한 다른 학생에게 별명으로 보여 줍니다. 반응은 정해진 문구만 쓰고 순위·인기순은 없습니다. 언제든 철회할 수 있고, 철회하면 공유물은 바로 비공개가 됩니다. 개발 시연 문구입니다.',
  required: false,
}

function isPlanMonday(date:string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) && new Date(date+'T00:00:00Z').getUTCDay()===1
}
function themeById(id: string) {
  const t = retentionState.themes.find((x) => x.themeId === id)
  if (!t) fail(404, 'NOT_FOUND', '테마를 찾을 수 없습니다.')
  return t!
}
function themeInput(raw: unknown): Omit<MockWeeklyTheme, 'themeId' | 'status' | 'updatedAt'> {
  const b = (raw ?? {}) as Record<string, unknown>
  const days = Array.isArray(b.days) ? (b.days as { day?: unknown; missionId?: unknown }[]) : []
  if (typeof b.grade !== 'string' || !Object.hasOwn(THEME_GRADE_LABELS, b.grade)) fail(422, 'VALIDATION_FAILED', '학년을 확인해 주세요.')
  if (typeof b.weekStart !== 'string' || new Date(`${b.weekStart}T00:00:00Z`).getUTCDay() !== 1)
    fail(422, 'VALIDATION_FAILED', '주 시작일은 월요일이어야 합니다.')
  if (typeof b.title !== 'string' || !b.title.trim()) fail(422, 'VALIDATION_FAILED', '제목을 적어 주세요.')
  return {
    grade: b.grade as MockWeeklyTheme['grade'],
    weekStart: b.weekStart as string,
    title: (b.title as string).trim(),
    intro: typeof b.intro === 'string' ? b.intro : '',
    days: THEME_DAYS.map((day): { day: ThemeDay; missionId: string } => ({
      day,
      missionId: String(days.find((d) => d.day === day)?.missionId ?? ''),
    })),
  }
}
/** 게시 검사(목업): 다섯 요일 모두 채움·서로 다른 생각 유형·같은 학년·주 게시 1개. */
async function publishErrors(t: MockWeeklyTheme) {
  const errors: string[] = []
  const grade = Number(t.grade.slice(1))
  // 관리자 미션 목업 중 게시된 미션만, 게시판(또는 현재판)의 학년·유형으로 검사한다.
  const byId = new Map(
    adminMissions
      .filter((m) => m.status === 'PUBLISHED')
      .flatMap((m) => {
        const v = m.versions.find((x) => x.version === (m.publishedVersion ?? m.currentVersion))
        return v && v.gradeMin <= grade && v.gradeMax >= grade ? [[m.missionId, v] as const] : []
      }),
  )
  if (t.days.some((d) => !d.missionId)) errors.push('비어 있는 요일이 있습니다.')
  if (t.days.some((d) => d.missionId && !byId.has(d.missionId))) errors.push('학년에 맞지 않거나 게시되지 않은 미션이 있습니다.')
  const types = t.days.map((d) => byId.get(d.missionId)?.thinkingType).filter(Boolean)
  if (new Set(types).size !== THINKING_ORDER.length) errors.push('다섯 생각 유형이 하나씩 들어가야 합니다.')
  if (retentionState.themes.some((x) => x !== t && x.status === 'PUBLISHED' && x.grade === t.grade && x.weekStart === t.weekStart))
    errors.push('같은 학년·주에 이미 게시한 테마가 있습니다.')
  return errors
}
function itemFields(b: Partial<MockLookItem>) {
  if (typeof b.name !== 'string' || !b.name.trim()) fail(422, 'VALIDATION_FAILED', '이름을 적어 주세요.')
  if (!Number.isInteger(b.pricePoints) || b.pricePoints! < 1 || b.pricePoints! > 10000) fail(422, 'VALIDATION_FAILED', '필요 포인트를 확인해 주세요.')
  return { name: b.name!.trim(), pricePoints: b.pricePoints!, assetKey: typeof b.assetKey === 'string' ? b.assetKey : '' }
}
