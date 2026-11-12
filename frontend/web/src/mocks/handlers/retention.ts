import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import { http, HttpResponse } from 'msw/http'
import { ApiError } from '../../data/apiClient.ts'
import { REACTIONS } from '../../domain/retention.ts'
import type { Reaction } from '../../domain/retention.ts'
import {
  balanceOf,
  communityOf,
  consentOf,
  earn,
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
} from '../fixtures/retention.ts'
import { guard, mockStudent, mockStudentHome, respond } from './student.ts'
import { consentRows, docs, fixtureConsent, parentChild } from './parent.ts'
import { allow } from './admin.ts'
import { THEME_DAYS } from '../../domain/retention.ts'
import type { ItemSlot, ThemeDay } from '../../domain/retention.ts'
import type { MockLookItem, MockWeeklyTheme } from '../fixtures/retention.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import { missions as adminMissions } from '../fixtures/admin/operations.ts'
import type { ConsentDocument } from '../../domain/parent.ts'

/**
 * 2026-11-06 결정(에픽 #396) 학생·학부모 참여 기능 목업. 계약은 API 명세 2.9~2.11(구현 예정).
 * core가 할 적립·해금·공개 판정을 화면 확인에 필요한 만큼만 흉내 낸다.
 */
const fail = (status: number, code: string, title: string): never => {
  throw new ApiError({ status, code, title })
}
const page = (request: Request) => {
  const q = new URL(request.url).searchParams
  return { page: Math.max(0, Number(q.get('page') ?? 0) || 0), size: Math.min(100, Math.max(1, Number(q.get('size') ?? 20) || 20)) }
}
const saved = <T>(value: T) => {
  persistRetention()
  return value
}
const isReaction = (v: unknown): v is Reaction => typeof v === 'string' && (REACTIONS as string[]).includes(v)
const postView = (p: (typeof retentionState.posts)[number]) => ({
  postId: p.postId,
  missionId: p.missionId,
  missionTitle: p.missionTitle,
  answer: p.answer,
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
      const key = request.headers.get('Idempotency-Key')
      if (!key || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(key))
        fail(400, 'VALIDATION_FAILED', 'Idempotency-Key(UUID)가 필요합니다.')
      const itemKey = decodeURIComponent(String(params.itemKey))
      const receipt = `${me.id}:${key}`
      if (retentionState.unlockKeys[receipt]) {
        if (retentionState.unlockKeys[receipt] !== itemKey) fail(409, 'IDEMPOTENCY_KEY_REUSED', '다른 요청에 쓴 키입니다.')
        return retentionState.unlockResults[receipt] ?? { itemKey, unlocked: true, balance: balanceOf(me.id) }
      }
      const item = lookCatalog(me.id).find((i) => i.itemKey === itemKey) ??
        // 판매 중단 아이템은 목록에서 빠지므로 관리자 목록으로 한 번 더 찾는다.
        retentionState.items.filter((i) => i.code === itemKey).map((i) => ({ itemKey: i.code, pricePoints: i.pricePoints, unlocked: false, onSale: false }))[0]
      if (!item) fail(404, 'LOOK_ITEM_NOT_FOUND', '없는 꾸미기 항목입니다.')
      if (item!.unlocked || isUnlocked(me.id, itemKey)) {
        const result = { itemKey, unlocked: true as const, balance: balanceOf(me.id) }
        retentionState.unlockKeys[receipt] = itemKey
        retentionState.unlockResults[receipt] = result
        return saved(result)
      }
      if (!item!.onSale) fail(409, 'LOOK_ITEM_NOT_ON_SALE', '지금은 해금할 수 없는 항목이에요.')
      if (balanceOf(me.id) < item!.pricePoints) fail(409, 'INSUFFICIENT_POINTS', '포인트가 모자라요.')
      retentionState.ledger[me.id].push({ eventType: 'UNLOCK', amount: -item!.pricePoints, createdAt: new Date().toISOString(), sourceKey: receipt })
      unlockedOf(me.id).push(itemKey)
      retentionState.unlockKeys[receipt] = itemKey
      const result = { itemKey, unlocked: true as const, balance: balanceOf(me.id) }
      retentionState.unlockResults[receipt] = result
      return saved(result)
    }),
  ),

  // ---------- 주간 테마·되돌아보기 (2.11) ----------
  http.get('/api/v1/students/me/weekly-theme', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const week = weeklyThemeFor(me.id, (await mockStudentHome(me)).missions, me.grade, me.plan)
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
      if (!weekRules(mockWeekday(), me.plan).weekend) fail(409, 'THEME_REVIEW_NOT_ALLOWED', '되돌아보기는 토요일에 열려요.')
      const key = `${me.id}:${weekStart()}`
      const first = !retentionState.reviewViews.includes(key)
      if (first) retentionState.reviewViews.push(key)
      earn(me.id, 'REVIEW_VIEWED', key)
      const week = weeklyThemeFor(me.id, (await mockStudentHome(me)).missions, me.grade, me.plan)
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
      const week = weeklyThemeFor(me.id, (await mockStudentHome(me)).missions, me.grade, me.plan)
      if (weekRules(mockWeekday(), me.plan).closed || (kind === 'OUTRO' && week.ending !== 'ENDED'))
        fail(409, 'THEME_STORY_NOT_ALLOWED', '지금은 이 이야기를 기록할 수 없어요.')
      const key = `${me.id}:${weekStart()}:${kind}`
      const first = !retentionState.storyViews.includes(key)
      if (first) retentionState.storyViews.push(key)
      return saved({ kind, firstViewThisWeek: first })
    }),
  ),
  // 큰 질문 정답 고르기(learning #484 판정 흉내): 금요일 문제 마무리 뒤 한 주 한 번, 후보 밖은 400.
  http.post('/api/v1/students/me/weekly-theme/answer-picks', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = mockStudent()
      const { pick } = ((await request.json().catch(() => ({}))) ?? {}) as { pick?: unknown }
      if (typeof pick !== 'string' || !pick.trim()) fail(400, 'VALIDATION_FAILED', '고를 후보를 확인해 주세요.')
      const missions = (await mockStudentHome(me)).missions
      const week = weeklyThemeFor(me.id, missions, me.grade, me.plan)
      const key = `${me.id}:${weekStart()}`
      if (!week.candidates?.includes(pick as string)) fail(400, 'VALIDATION_FAILED', '후보 중에서 골라 주세요.')
      if (weekRules(mockWeekday(), me.plan).closed || week.days[4]?.attemptStatus !== 'COMPLETED' || retentionState.picks[key])
        fail(409, 'THEME_PICK_NOT_ALLOWED', '지금은 정답을 고를 수 없어요.')
      retentionState.picks[key] = { pick: pick as string, correct: pick === MOCK_STORY.answer, at: new Date().toISOString() }
      const after = weeklyThemeFor(me.id, missions, me.grade, me.plan)
      return saved({ correct: pick === MOCK_STORY.answer, ending: after.ending, answer: after.answer })
    }),
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
            author: { nickname: x.nickname, look: { companion: x.companion } },
            answer: x.answer,
            myReactions: retentionState.reactions[x.postId]?.[me.id] ?? [],
            createdAt: x.createdAt,
          })),
      })
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
    const body = (await request.clone().json().catch(() => null)) as { targetType?: string; targetId?: string } | null
    if (body?.targetType !== 'COMMUNITY_POST') return undefined
    return respond(async () => {
      guard(request)
      mockStudent()
      const post = retentionState.posts.find((p) => p.postId === body.targetId)
      if (!post) fail(404, 'COMMUNITY_POST_NOT_FOUND', '볼 수 없는 글이에요.')
      post!.status = 'HIDDEN_REPORT'
      return saved({ reportId: `report-${post!.postId}`, status: 'RECEIVED', targetType: 'COMMUNITY_POST', targetId: post!.postId })
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
  http.get('/api/v1/admin/weekly-themes', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const q = new URL(request.url).searchParams
      const items = retentionState.themes.filter(
        (t) =>
          (!q.get('grade') || t.grade === q.get('grade')) &&
          (!q.get('status') || t.status === q.get('status')) &&
          (!q.get('weekStart') || t.weekStart === q.get('weekStart')),
      )
      return { items, page: 0, size: items.length, totalElements: items.length }
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
      retentionState.themes.unshift(t)
      return saved(t)
    }, 201),
  ),
  http.get('/api/v1/admin/weekly-themes/:themeId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      return themeById(String(params.themeId))
    }),
  ),
  http.put('/api/v1/admin/weekly-themes/:themeId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const t = themeById(String(params.themeId))
      if (t.status === 'REVIEW_REQUIRED') fail(409, 'WEEKLY_THEME_IN_REVIEW', '검토 중인 테마는 수정할 수 없습니다.')
      // 게시 중 수정은 재검토: 작성 상태로 돌린다.
      Object.assign(t, themeInput(await request.json()), { status: 'DRAFT', updatedAt: new Date().toISOString() })
      return saved(t)
    }),
  ),
  ...(['review-request', 'publish', 'unpublish'] as const).map((action) =>
    http.post(`/api/v1/admin/weekly-themes/:themeId/${action}`, ({ request, params }) =>
      respond(async () => {
        allow(request, 'CONTENT')
        const t = themeById(String(params.themeId))
        if (action === 'review-request') {
          if (t.status !== 'DRAFT') fail(409, 'INVALID_STATE', '작성 중인 테마만 검토를 요청할 수 있습니다.')
          t.status = 'REVIEW_REQUIRED'
        } else if (action === 'publish') {
          if (t.status !== 'REVIEW_REQUIRED') fail(409, 'INVALID_STATE', '검토 요청한 테마만 게시할 수 있습니다.')
          const errors = await publishErrors(t)
          if (errors.length)
            throw new ApiError({
              status: 422,
              code: 'WEEKLY_THEME_PUBLISH_INCOMPLETE',
              title: '게시 검사를 통과하지 못했습니다.',
              errors: errors.map((message) => ({ message })),
            } as never)
          t.status = 'PUBLISHED'
        } else {
          if (t.status !== 'PUBLISHED') fail(409, 'INVALID_STATE', '게시 중인 테마만 중단할 수 있습니다.')
          t.status = 'UNPUBLISHED'
        }
        t.updatedAt = new Date().toISOString()
        return saved(t)
      }),
    ),
  ),
  http.get('/api/v1/admin/look-items', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const items = retentionState.items
      return { items, page: 0, size: items.length, totalElements: items.length }
    }),
  ),
  http.post('/api/v1/admin/look-items', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const b = (await request.json()) as Partial<MockLookItem>
      if (typeof b.code !== 'string' || !/^[A-Z0-9_]{3,40}$/.test(b.code)) fail(422, 'VALIDATION_FAILED', '코드를 확인해 주세요.')
      if (retentionState.items.some((i) => i.code === b.code)) fail(409, 'LOOK_ITEM_CODE_DUPLICATE', '이미 있는 코드입니다.')
      if (!['HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND'].includes(String(b.slot))) fail(422, 'VALIDATION_FAILED', '칸을 확인해 주세요.')
      const item: MockLookItem = {
        itemId: `look-${crypto.randomUUID().slice(0, 8)}`,
        code: b.code!,
        slot: b.slot as ItemSlot,
        ...itemFields(b),
        status: 'ON_SALE',
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
