import test from 'node:test'
import assert from 'node:assert/strict'
import {
  isLookUnlocked,
  readCommunityPosts,
  readLookItems,
  readMyPosts,
  readPoints,
  readWeeklyTheme,
  todayThemeDay,
} from '../src/domain/retention.ts'
import { readLook } from '../src/domain/studentLook.ts'
import { isAccountDocument, reportPeriodType } from '../src/domain/parent.ts'
import { retentionApi } from '../src/data/retention/api.ts'
import { studentLookApi } from '../src/data/studentLook/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'

test.afterEach(() => setAccessToken(null))

test('포인트·해금 목록은 모르는 사건·칸을 버리고 숫자가 아니면 0으로 둔다', () => {
  assert.deepEqual(
    readPoints({ balance: 'x', items: [{ eventType: 'UNLOCK', amount: -100, createdAt: 't' }, { eventType: 'RANK', amount: 9, createdAt: 't' }] }),
    { balance: 0, items: [{ eventType: 'UNLOCK', amount: -100, createdAt: 't' }] },
  )
  const items = readLookItems({ items: [{ itemKey: 'THEME:space', slot: 'THEME', pricePoints: 100, unlocked: false }, { itemKey: 'x', slot: 'SHOES' }] })
  assert.equal(items.length, 1)
  assert.equal(items[0].onSale, true, 'onSale 생략은 판매 중')
  assert.equal(isLookUnlocked(items, 'THEME:space'), false)
  assert.equal(isLookUnlocked(undefined, 'THEME:lake'), true, '호수·뭉치는 목록이 없어도 열림')
  assert.equal(isLookUnlocked(undefined, 'COMPANION:mungchi'), true)
})

test('꾸미기 설정은 서버가 equipped를 줄 때만 슬롯을 만든다(#234 현행 응답 호환)', () => {
  assert.equal('equipped' in readLook({ theme: 'sea', companion: 'tori' }), false)
  assert.deepEqual(readLook({ theme: 'sea', companion: 'tori', equipped: { HAT: 'HAT_ACORN', OUTFIT: 3 } }).equipped, {
    HAT: 'HAT_ACORN',
    OUTFIT: null,
    ACCESSORY: null,
    BACKGROUND: null,
  })
})

test('주간 테마: 테마가 없으면 null, 요일·유형이 틀린 항목은 버린다', () => {
  assert.equal(readWeeklyTheme(null), null)
  assert.equal(readWeeklyTheme({ title: '없음' }), null)
  const theme = readWeeklyTheme({
    themeId: 't1',
    weekStart: '2026-11-09',
    title: '테마',
    intro: '',
    days: [
      { day: 'MON', missionId: 'm1', thinkingType: 'ANALYZE', state: 'CLOSED', attemptStatus: 'COMPLETED' },
      { day: 'TUE', missionId: 'm2', thinkingType: 'EVALUATE', state: 'OPEN', attemptStatus: 'NOT_STARTED' },
      { day: 'SAT', missionId: 'm3', thinkingType: 'CREATE' },
      { day: 'WED', missionId: 'm4', thinkingType: 'LEVEL' },
    ],
    review: { open: false, missions: [] },
  })!
  assert.equal(theme.intro, null, '빈 도입 이야기는 없음으로')
  assert.deepEqual(theme.days.map((d) => d.day), ['MON', 'TUE'])
  assert.equal(todayThemeDay(theme)?.missionId, 'm2')
})

test('커뮤니티 응답은 반응 수·학생 ID 없이 읽고, 내 글만 반응 수를 센다', () => {
  const [post] = readCommunityPosts({
    items: [{ postId: 'p1', studentId: 'secret', author: { nickname: '하늘', look: { companion: 'kongi' } }, answer: { text: '까닭' }, myReactions: ['NEW_IDEA', 'LIKE'], reactionCount: 9 }],
  })
  assert.deepEqual(post, { postId: 'p1', author: { nickname: '하늘', companion: 'kongi' }, answer: '까닭', myReactions: ['NEW_IDEA'], createdAt: '' })
  const [mine] = readMyPosts({ items: [{ postId: 'p2', missionTitle: '미션', status: 'HIDDEN_REPORT', reactions: { CLEAR_REASON: 2 } }] })
  assert.equal(mine.status, 'HIDDEN_REPORT')
  assert.deepEqual(mine.reactions, { NEW_IDEA: 0, CLEAR_REASON: 2, DIFFERENT_VIEW: 0, WANT_MORE: 0 })
})

test('동의 문서 구분과 리포트 종류 기본값', () => {
  assert.equal(isAccountDocument({ kind: 'TERMS' }), true)
  assert.equal(isAccountDocument({ kind: 'COMMUNITY' }), false, '선택 동의는 가입 필수 문서가 아님')
  assert.equal(reportPeriodType({}), 'WEEKLY')
  assert.equal(reportPeriodType({ periodType: 'DAILY' }), 'DAILY')
})

test('참여 어댑터는 명세 경로·메서드·멱등 키를 보낸다', async (t) => {
  const calls: { url: string; init: RequestInit }[] = []
  setAccessToken('synthetic-student', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init })
    return new Response(null, { status: 204 })
  })
  await retentionApi.unlock('THEME:space', 'key-1')
  await retentionApi.react('p1', 'WANT_MORE', true)
  await retentionApi.react('p1', 'WANT_MORE', false)
  await retentionApi.recordReviewView()
  await retentionApi.reportPost('p1', '이상해요', 'key-2')
  await studentLookApi.save({ theme: 'lake', companion: 'mungchi', equipped: { HAT: 'HAT_ACORN', OUTFIT: null, ACCESSORY: null, BACKGROUND: null } }).catch(() => {})
  assert.deepEqual(
    calls.map((c) => `${c.init.method} ${c.url}`),
    [
      'POST /api/v1/students/me/look-items/THEME%3Aspace/unlock',
      'PUT /api/v1/community-posts/p1/reactions/WANT_MORE',
      'DELETE /api/v1/community-posts/p1/reactions/WANT_MORE',
      'POST /api/v1/students/me/weekly-theme/review-views',
      'POST /api/v1/error-reports',
      'PUT /api/v1/students/me/preferences',
    ],
  )
  assert.equal(new Headers(calls[0].init.headers).get('Idempotency-Key'), 'key-1')
  assert.equal(new Headers(calls[4].init.headers).get('Idempotency-Key'), 'key-2')
  assert.deepEqual(JSON.parse(String(calls[4].init.body)), { targetType: 'COMMUNITY_POST', targetId: 'p1', category: 'INAPPROPRIATE', comment: '이상해요' })
  assert.equal(JSON.parse(String(calls[5].init.body)).equipped.HAT, 'HAT_ACORN')
})
