import test from 'node:test'
import assert from 'node:assert/strict'
import {
  clueCount,
  dayAction,
  dayContext,
  isLookUnlocked,
  onTimeCount,
  remainingCandidates,
  readCommunityPosts,
  readLookItems,
  readMyPosts,
  readAnswerPick,
  pickStage,
  readPoints,
  readThemeMotion,
  readWeeklyTheme,
  POINT_RULES,
  storyToShow,
  themeClosed,
  todayThemeDay,
} from '../src/domain/retention.ts'
import { readLook } from '../src/domain/studentLook.ts'
import { isAccountDocument, reportPeriodType } from '../src/domain/parent.ts'
import { retentionApi } from '../src/data/retention/api.ts'
import { studentLookApi } from '../src/data/studentLook/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'

test.afterEach(() => setAccessToken(null))

test('포인트는 실제 페이지 정보를 보존하고 잘못된 잔액·목록은 성공으로 바꾸지 않는다', () => {
  const entry = { eventType: 'UNLOCK', amount: -100, createdAt: '2026-11-09T00:00:00Z' }
  const value = { balance: 50, items: [entry], page: 1, size: 20, totalElements: 21 }
  assert.deepEqual(readPoints(value), value)
  for (const invalid of [{ ...value, balance: '50' }, { ...value, balance: -1 }, { ...value, items: null }, { ...value, size: 0 }])
    assert.throws(() => readPoints(invalid), /확인하지 못/)
  assert.throws(() => readLookItems({}), /확인하지 못/)
  const item = { itemKey: 'THEME:space', name: '소행성', slot: 'THEME' as const, pricePoints: 100, unlocked: false, onSale: true, assetKey: null }
  assert.deepEqual(readLookItems({ items: [item, { itemKey: 'x', slot: 'SHOES' }] }), [item])
  assert.throws(() => readLookItems({ items: [{ ...item, pricePoints: '100' }] }), /확인하지 못/)
  assert.equal(isLookUnlocked([item], 'THEME:space'), false)
  assert.equal(isLookUnlocked(undefined, 'THEME:lake'), true)
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
  // #484 칸이 없던 응답도 기본값으로 읽는다(엔딩 전·후보 없음·움직임 없음).
  assert.deepEqual(
    [theme.ending, theme.finished, theme.candidates, theme.introMotion, theme.days[0].clue, theme.days[0].completedOnDay],
    ['NOT_ENDED', false, [], null, null, false],
  )
})

const motion = {
  version: 1,
  transition: { kind: 'fade', seconds: 0.6 },
  camera: { from: { x: 50, y: 50, zoom: 1 }, to: { x: 40, y: 45, zoom: 1.2 }, seconds: 12 },
  speakers: { 뭉치: { x: 30, y: 60, zoom: 1.1 } },
  effects: [{ shape: 'leaf', color: '#88AA44', count: 8, size: 2, direction: 120, speed: 6, opacity: 0.5 }],
  captions: [{ start: 0, end: 4.25, text: '마을에 밤이 왔어요' }],
  extra: 'ignored',
}

test('주간 테마 #438·#484 칸: 단서·엔딩·이야기 그림·움직임을 읽는다', () => {
  const theme = readWeeklyTheme({
    themeId: 't1', weekStart: '2026-11-09', title: '시계탑', intro: '시작', reused: false,
    days: [{ day: 'MON', missionId: 'm1', thinkingType: 'ANALYZE', state: 'OPEN', attemptStatus: 'COMPLETED', clue: '도토리가 없어요', rulesOut: ['다람쥐'], completedOnDay: true }],
    review: { open: false, missions: [] }, completed: false, finished: true, ending: 'ENDED',
    bigQuestion: '누구일까?', candidates: ['다람쥐', '부엉이', 3], introImageUrl: 'https://s3/intro.png', introVideoUrl: null,
    introMotion: motion, introSeen: true, outroSeen: false, outro: '끝', outroImageUrl: null, outroVideoUrl: 'https://s3/outro.mp4',
    outroMotion: { ...motion, version: 2 }, answer: '부엉이', answerClue: '깃털',
  })!
  assert.deepEqual(theme.days[0], {
    day: 'MON', missionId: 'm1', thinkingType: 'ANALYZE', state: 'OPEN', attemptStatus: 'COMPLETED',
    clue: '도토리가 없어요', rulesOut: ['다람쥐'], completedOnDay: true,
  })
  assert.deepEqual(theme.candidates, ['다람쥐', '부엉이'], '문자열 아닌 후보는 버림')
  assert.equal(theme.introMotion?.camera?.to.zoom, 1.2)
  assert.equal('extra' in theme.introMotion!, false, '모르는 칸은 버림')
  assert.deepEqual(theme.introMotion?.spots, [], 'spots가 없으면 빈 배열')
  assert.equal(theme.outroMotion, null, '형식 v1이 아니면 그림만')
  assert.deepEqual([theme.ending, theme.finished, theme.answer, theme.outroVideoUrl], ['ENDED', true, '부엉이', 'https://s3/outro.mp4'])
})

test('움직임 v1 범위를 하나라도 벗어나면 null', () => {
  assert.notEqual(readThemeMotion(motion), null)
  assert.notEqual(readThemeMotion({ ...motion, camera: null }), null, '카메라는 없어도 됨')
  for (const bad of [
    null, [], { ...motion, transition: { kind: 'spin', seconds: 0.6 } }, { ...motion, transition: { kind: 'fade', seconds: 2 } },
    { ...motion, camera: { ...motion.camera, seconds: 5 } }, { ...motion, speakers: { 뭉치: { x: 30, y: 60, zoom: 2 } } },
    { ...motion, effects: [motion.effects[0], motion.effects[0], motion.effects[0]] },
    { ...motion, effects: [{ ...motion.effects[0], color: 'red' }] }, { ...motion, effects: [{ ...motion.effects[0], count: 1.5 }] },
    { ...motion, captions: [{ start: 3, end: 1, text: '거꾸로' }] }, { ...motion, captions: [{ start: 0, end: 1, text: '가'.repeat(31) }] },
    { ...motion, spots: [{ x: 10, y: 10, label: '', line: '말', evidence: true }] },
  ]) assert.equal(readThemeMotion(bad), null, JSON.stringify(bad)?.slice(0, 60))
})

test('먼저 띄울 이야기: 시작은 그 주 첫 진입, 종료는 엔딩 뒤 한 번, 무료 일요일은 없음', () => {
  const base = readWeeklyTheme({
    themeId: 't1', weekStart: '2026-11-09', title: '테마', intro: '시작',
    days: [{ day: 'MON', missionId: 'm1', thinkingType: 'ANALYZE', state: 'OPEN', attemptStatus: 'NOT_STARTED' }],
    review: { open: false, missions: [] },
  })!
  assert.equal(storyToShow(base), 'INTRO')
  assert.equal(storyToShow({ ...base, introSeen: true }), null)
  assert.equal(storyToShow({ ...base, intro: null }), null, '시작 이야기가 없는 수동 테마')
  const ended = { ...base, introSeen: true, ending: 'ENDED' as const, outro: '끝' }
  assert.equal(storyToShow(ended), 'OUTRO')
  assert.equal(storyToShow({ ...ended, outroSeen: true }), null)
  const sunday = { ...ended, days: base.days.map((d) => ({ ...d, state: 'CLOSED' as const })) }
  assert.equal(themeClosed(sunday), true)
  assert.equal(storyToShow(sunday), null, '무료 일요일은 새로 띄우지 않음')
  assert.equal(storyToShow({ ...sunday, review: { open: true, missions: [] } }), 'OUTRO', '프리미엄 일요일은 토요일과 같음')
})

test('요일별 할 수 있는 일(#484): 공개된 안 푼 문제 시작, 이어하기는 요일 무관, 다시 풀기는 토요일·프리미엄 일요일만', () => {
  const day = (d: string, state: string, attemptStatus: string, extra: Record<string, unknown> = {}) =>
    ({ day: d, missionId: `m-${d}`, thinkingType: 'ANALYZE', state, attemptStatus, ...extra })
  const week = (open: boolean, days: ReturnType<typeof day>[]) =>
    readWeeklyTheme({ themeId: 't', weekStart: '2026-11-09', title: '테마', days, review: { open, missions: [] }, candidates: ['가', '나', '다', '라'] })!
  const wed = week(false, [
    day('MON', 'OPEN', 'COMPLETED', { clue: '단서1', rulesOut: ['가'], completedOnDay: true }),
    day('TUE', 'OPEN', 'NOT_STARTED'),
    day('WED', 'OPEN', 'IN_PROGRESS'),
    day('THU', 'LOCKED', 'NOT_STARTED'),
    day('FRI', 'LOCKED', 'NOT_STARTED'),
  ])
  assert.deepEqual(wed.days.map((d) => dayAction(wed, d)), ['DONE', 'START', 'RESUME', 'LOCKED', 'LOCKED'])
  assert.deepEqual(wed.days.map((d) => dayContext(dayAction(wed, d))), [null, 'THEME_DAY', null, null, null])
  assert.equal(todayThemeDay(wed)?.day, 'WED', '쌓여 열린 문제 중 마지막이 오늘')
  assert.deepEqual([remainingCandidates(wed), clueCount(wed), onTimeCount(wed)], [['나', '다', '라'], 1, 1])

  const sat = week(true, [
    day('MON', 'OPEN', 'COMPLETED', { clue: '단서1', rulesOut: ['가'] }),
    day('TUE', 'OPEN', 'NOT_STARTED'),
    day('WED', 'OPEN', 'COMPLETED', { clue: '힌트', rulesOut: [] }),
    day('THU', 'OPEN', 'COMPLETED', { clue: '단서4', rulesOut: ['나', '다'] }),
    day('FRI', 'OPEN', 'IN_PROGRESS'),
  ])
  assert.deepEqual(sat.days.map((d) => dayAction(sat, d)), ['REDO', 'START', 'REDO', 'REDO', 'RESUME'])
  assert.equal(dayContext('REDO'), 'THEME_REVIEW')
  assert.equal(todayThemeDay(sat), null, '토요일엔 오늘 문제(당일 풀이)가 없음')
  assert.deepEqual([remainingCandidates(sat), clueCount(sat)], [['라'], 3], '빈 rulesOut(힌트) 단서도 단서 수에 셈')

  const freeSunday = week(false, [day('MON', 'CLOSED', 'COMPLETED'), day('TUE', 'CLOSED', 'NOT_STARTED'), day('WED', 'CLOSED', 'IN_PROGRESS')])
  assert.deepEqual(freeSunday.days.map((d) => dayAction(freeSunday, d)), ['DONE', 'CLOSED', 'RESUME'], '무료 일요일도 진행 중 시도는 이어하기')
  assert.equal(todayThemeDay(freeSunday), null)
})

test('정답 고르기 결과: 엔딩 전에는 정답을 버리고, 모양이 틀리면 실패로 본다', () => {
  assert.deepEqual(readAnswerPick({ correct: false, ending: 'NOT_ENDED', answer: '새어 나온 정답' }), { correct: false, ending: 'NOT_ENDED', answer: null })
  assert.deepEqual(readAnswerPick({ correct: true, ending: 'ENDED', answer: '부엉이' }), { correct: true, ending: 'ENDED', answer: '부엉이' })
  assert.throws(() => readAnswerPick({ correct: 'yes', ending: 'ENDED' }), /정답 확인/)
})

test('정답 고르기 단계(#484·#590): 금요일 학습 완료 뒤 한 번, 틀리면 다시 고르지 않고 다시 풀기 대기, 엔딩 뒤 맞았는지 구분', () => {
  const day = (d: string, state: string, attemptStatus: string) => ({ day: d, missionId: `m-${d}`, thinkingType: 'ANALYZE', state, attemptStatus })
  const days = (fri: string, state = 'OPEN') =>
    ['MON', 'TUE', 'WED', 'THU'].map((d) => day(d, state, 'COMPLETED')).concat(day('FRI', state, fri))
  const theme = (extra: Record<string, unknown>) =>
    readWeeklyTheme({ themeId: 't', weekStart: '2026-11-09', title: '테마', days: days('COMPLETED'), review: { open: false, missions: [] },
      bigQuestion: '누구일까?', candidates: ['가', '나', '다', '라'], ...extra })!
  assert.equal(theme({}).answerPick, null, '고르지 않으면 null')
  assert.equal(pickStage(theme({})), 'READY')
  assert.equal(pickStage(theme({ days: days('IN_PROGRESS') })), 'LOCKED', '금요일 문제 학습 완료 전')
  assert.equal(pickStage(theme({ days: days('COMPLETED', 'CLOSED') })), 'CLOSED', '무료 일요일')
  assert.equal(pickStage(theme({ candidates: [] })), 'NONE', '후보 없는 테마')

  const wrong = theme({ answerPick: { pick: '가', correct: false } })
  assert.deepEqual(wrong.answerPick, { pick: '가', correct: false })
  assert.equal(pickStage(wrong), 'RETRY', '틀리면 다시 고르지 않음')
  assert.equal(pickStage(theme({ answerPick: { pick: '가', correct: false }, review: { open: true, missions: [] } })), 'RETRY', '토요일도 다시 풀기 마무리 전까지')
  const endedWrong = theme({ answerPick: { pick: '가', correct: false }, ending: 'ENDED', answer: '라' })
  const endedRight = theme({ answerPick: { pick: '라', correct: true }, ending: 'ENDED', answer: '라' })
  assert.deepEqual([pickStage(endedWrong), endedWrong.answerPick?.correct, pickStage(endedRight), endedRight.answerPick?.correct], ['ENDED', false, 'ENDED', true])
  assert.equal(theme({ answerPick: { pick: '가' } }).answerPick, null, '모양이 틀리면 고르지 않은 것으로 읽음')
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
    return String(url).endsWith('/unlock') ? Response.json({ itemKey: 'THEME:space', unlocked: true, balance: 50 }) : new Response(null, { status: 204 })
  })
  await retentionApi.unlock('THEME:space', 'key-1')
  await retentionApi.react('p1', 'WANT_MORE', true)
  await retentionApi.react('p1', 'WANT_MORE', false)
  await retentionApi.recordReviewView()
  await retentionApi.recordStoryView('INTRO')
  await retentionApi.pickAnswer('부엉이').catch(() => {})
  await retentionApi.reportPost('p1', '이상해요', 'key-2')
  await studentLookApi.save({ theme: 'lake', companion: 'mungchi', equipped: { HAT: 'HAT_ACORN', OUTFIT: null, ACCESSORY: null, BACKGROUND: null } }).catch(() => {})
  assert.deepEqual(
    calls.map((c) => `${c.init.method} ${c.url}`),
    [
      'POST /api/v1/students/me/look-items/THEME%3Aspace/unlock',
      'PUT /api/v1/community-posts/p1/reactions/WANT_MORE',
      'DELETE /api/v1/community-posts/p1/reactions/WANT_MORE',
      'POST /api/v1/students/me/weekly-theme/review-views',
      'POST /api/v1/students/me/weekly-theme/story-views',
      'POST /api/v1/students/me/weekly-theme/answer-picks',
      'POST /api/v1/error-reports',
      'PUT /api/v1/students/me/preferences',
    ],
  )
  assert.equal(new Headers(calls[0].init.headers).get('Idempotency-Key'), 'key-1')
  assert.deepEqual(JSON.parse(String(calls[4].init.body)), { kind: 'INTRO' })
  assert.deepEqual(JSON.parse(String(calls[5].init.body)), { pick: '부엉이' })
  assert.ok([calls[4], calls[5]].every((c) => c.init.cache === 'no-store'))
  assert.equal(new Headers(calls[6].init.headers).get('Idempotency-Key'), 'key-2')
  assert.deepEqual(JSON.parse(String(calls[6].init.body)), { targetType: 'COMMUNITY_POST', targetId: 'p1', category: 'INAPPROPRIATE', comment: '이상해요' })
  assert.equal(JSON.parse(String(calls[7].init.body)).equipped.HAT, 'HAT_ACORN')
})


test('#389 실제 조회·해금 응답과 assetKey를 보존하고 HTTP 캐시를 재사용하지 않는다', async t => {
  setAccessToken('synthetic-student', 'STUDENT')
  const calls: { url: string; init: RequestInit }[] = []
  const points = { balance: 120, items: [], page: 2, size: 20, totalElements: 40 }
  const item = { itemKey: 'HAT_ACORN', slot: 'HAT', name: '도토리 모자', pricePoints: 40, unlocked: false, onSale: true, assetKey: 'looks/hat-acorn.svg' }
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init })
    return Response.json(String(url).endsWith('/unlock') ? { itemKey: item.itemKey, unlocked: true, balance: 80 }
      : String(url).endsWith('/look-items') ? { items: [item] } : points)
  })
  assert.deepEqual(await retentionApi.myPoints(undefined, 2), points)
  assert.deepEqual(await retentionApi.childPoints('child/id', undefined, 2), points)
  assert.deepEqual(await retentionApi.lookItems(), [item])
  assert.deepEqual(await retentionApi.unlock(item.itemKey, crypto.randomUUID()), { itemKey: item.itemKey, unlocked: true, balance: 80 })
  assert.equal(calls[0].url, '/api/v1/students/me/points?page=2&size=20')
  assert.equal(calls[1].url, '/api/v1/children/child%2Fid/points?page=2&size=20')
  assert.ok(calls.every(call => call.init.cache === 'no-store'))
  assert.equal(calls[3].init.body, undefined)
})

test('당일 풀이·주간 완주는 learning #484 판정 칸으로 적립되어 준비 중 표시 없이 안내한다(#506)', () => {
  assert.deepEqual(
    POINT_RULES.filter((r) => r.type === 'THEME_ON_TIME' || r.type === 'THEME_FINISHED').map((r) => [r.type, r.amount]),
    [['THEME_ON_TIME', 5], ['THEME_FINISHED', 10]],
  )
  assert.ok(POINT_RULES.every((r) => !('preparing' in r)))
})
