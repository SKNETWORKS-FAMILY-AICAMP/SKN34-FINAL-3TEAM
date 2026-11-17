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
  readFriendRoom,
  readLookItems,
  readMyPosts,
  readAnswerPick,
  pickStage,
  readPoints,
  readWeeklyTheme,
  knownFacts,
  candidateFacts,
  ruledOutOn,
  POINT_RULES,
  storyToShow,
  endingDue,
  themeClosed,
  todayThemeDay,
  wornAssets,
  journalTab,
  isAttemptContext,
  ALL_ITEM_SLOTS,
  DECOR_MAX_OWNED,
  readDecorPurchaseResult,
  readEquipped,
  SLOT_LABELS,
} from '../src/domain/retention.ts'
import { readLook } from '../src/domain/studentLook.ts'
import { canBuyMore, createIdempotencyKeys, keepIdempotencyKey, unlockMessage } from '../src/presentation/student/world/lookShop.ts'
// 움직임 읽기는 domain/themeMotion.ts 하나(#440에서 retention.ts 중복 정리)
import { readThemeMotion } from '../src/domain/themeMotion.ts'
import { isAccountDocument, reportPeriodType } from '../src/domain/parent.ts'
import { retentionApi } from '../src/data/retention/api.ts'
import { studentLookApi } from '../src/data/studentLook/api.ts'
import { ApiError, setAccessToken } from '../src/data/apiClient.ts'

test.afterEach(() => setAccessToken(null))

test('포인트는 실제 페이지 정보를 보존하고 잘못된 잔액·목록은 성공으로 바꾸지 않는다', () => {
  const entry = { eventType: 'UNLOCK', amount: -100, createdAt: '2026-11-09T00:00:00Z' }
  const value = { balance: 50, items: [entry], page: 1, size: 20, totalElements: 21 }
  assert.deepEqual(readPoints(value), value)
  for (const invalid of [{ ...value, balance: '50' }, { ...value, balance: -1 }, { ...value, items: null }, { ...value, size: 0 }])
    assert.throws(() => readPoints(invalid), /확인하지 못/)
  assert.throws(() => readLookItems({}), /확인하지 못/)
  const item = { itemKey: 'THEME:space', name: '소행성', slot: 'THEME' as const, pricePoints: 100, unlocked: false, onSale: true, assetKey: null, ownedCount: null, createdAt: null }
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
    clue: '도토리가 없어요', rulesOut: ['다람쥐'], completedOnDay: true, clueFeature: null, clueFacts: null,
  })
  assert.equal(theme.features, null, '특징 표가 없는 테마(#647 전·사람이 쓴 테마)는 null')
  assert.deepEqual(theme.candidates, ['다람쥐', '부엉이'], '문자열 아닌 후보는 버림')
  assert.equal(theme.introMotion?.camera?.to.zoom, 1.2)
  assert.equal('extra' in theme.introMotion!, false, '모르는 칸은 버림')
  assert.deepEqual(theme.introMotion?.spots, [], 'spots가 없으면 빈 배열')
  assert.equal(theme.outroMotion, null, '형식 v1이 아니면 그림만')
  assert.deepEqual([theme.ending, theme.finished, theme.answer, theme.outroVideoUrl], ['ENDED', true, '부엉이', 'https://s3/outro.mp4'])
})

test('단서 근거(#647): 얻은 요일 특징만 읽고, 후보마다 알아낸 것을 모은다', () => {
  const theme = readWeeklyTheme({
    themeId: 't1', weekStart: '2026-11-09', title: '시계탑', intro: '시작', reused: false,
    days: [
      { day: 'MON', missionId: 'm1', thinkingType: 'ANALYZE', state: 'OPEN', attemptStatus: 'COMPLETED', clue: '도토리가 없어요', rulesOut: ['다람쥐'],
        completedOnDay: true, clueFeature: '도토리를 먹나요', clueFacts: [{ candidate: '다람쥐', value: '먹어요' }, { candidate: '부엉이', value: '안 먹어요' }, { candidate: '부엉이', value: '' }, 7] },
      { day: 'TUE', missionId: 'm2', thinkingType: 'EVALUATE', state: 'OPEN', attemptStatus: 'NOT_STARTED', clue: null, rulesOut: null,
        completedOnDay: false, clueFeature: null, clueFacts: null },
    ],
    review: { open: false, missions: [] }, completed: false, finished: false, ending: 'NOT_ENDED',
    bigQuestion: '누구일까?', candidates: ['다람쥐', '부엉이'], introSeen: true, outroSeen: false,
    features: [{ name: '도토리를 먹나요', values: [{ candidate: '다람쥐', value: '먹어요' }] }, { name: 3, values: [] }],
  })!
  assert.equal(theme.days[0].clueFeature, '도토리를 먹나요')
  assert.deepEqual(theme.days[0].clueFacts, [{ candidate: '다람쥐', value: '먹어요' }, { candidate: '부엉이', value: '안 먹어요' }], '빈 값·모양 틀린 값은 버림')
  assert.equal(theme.days[1].clueFacts, null)
  assert.deepEqual(theme.features, [{ name: '도토리를 먹나요', values: [{ candidate: '다람쥐', value: '먹어요' }] }])
  assert.deepEqual(knownFacts(theme, '부엉이'), [{ day: 'MON', feature: '도토리를 먹나요', value: '안 먹어요' }])
  assert.equal(ruledOutOn(theme, '다람쥐'), 'MON')
  assert.equal(ruledOutOn(theme, '부엉이'), null)
})

test('#715 후보 카드 특징: 엔딩 전에는 푼 요일 단서만, 엔딩 뒤에는 특징 표 전체(건너뛴 요일은 learned false)', () => {
  const base = {
    themeId: 't1', weekStart: '2026-11-09', title: '시계탑', intro: '시작', reused: false,
    days: [
      { day: 'MON', missionId: 'm1', thinkingType: 'ANALYZE', state: 'OPEN', attemptStatus: 'COMPLETED', clue: '단서', rulesOut: ['다람쥐'],
        completedOnDay: true, clueFeature: '도토리를 먹나요', clueFacts: [{ candidate: '다람쥐', value: '먹어요' }, { candidate: '부엉이', value: '안 먹어요' }] },
      { day: 'TUE', missionId: 'm2', thinkingType: 'EVALUATE', state: 'OPEN', attemptStatus: 'NOT_STARTED', clue: null, rulesOut: null,
        completedOnDay: false, clueFeature: null, clueFacts: null },
    ],
    review: { open: false, missions: [] }, completed: false, finished: false,
    bigQuestion: '누구일까?', candidates: ['다람쥐', '부엉이'], introSeen: true, outroSeen: false,
  }
  const features = [
    { name: '도토리를 먹나요', values: [{ candidate: '다람쥐', value: '먹어요' }, { candidate: '부엉이', value: '안 먹어요' }] },
    { name: '밤에 깨어 있나요', values: [{ candidate: '다람쥐', value: '아니요' }, { candidate: '부엉이', value: '네' }] },
  ]
  const before = readWeeklyTheme({ ...base, ending: 'NOT_ENDED', features: null })!
  assert.deepEqual(candidateFacts(before, '부엉이'), [{ feature: '도토리를 먹나요', value: '안 먹어요', learned: true }], '엔딩 전에는 단서만')
  const after = readWeeklyTheme({ ...base, ending: 'ENDED', answer: '부엉이', features })!
  assert.deepEqual(candidateFacts(after, '부엉이'), [
    { feature: '도토리를 먹나요', value: '안 먹어요', learned: true },
    { feature: '밤에 깨어 있나요', value: '네', learned: false },
  ], '건너뛴 화요일 특징도 엔딩 뒤에는 보임')
  const noTable = readWeeklyTheme({ ...base, ending: 'ENDED', answer: '부엉이', features: null })!
  assert.deepEqual(candidateFacts(noTable, '부엉이'), [{ feature: '도토리를 먹나요', value: '안 먹어요', learned: true }], '표가 없으면 단서만')
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

test('문제를 마무리한 직후 이야기의 끝(#440): 엔딩이 됐고 아직 안 봤을 때만, 시작 이야기를 안 봤어도 종료가 우선', () => {
  const saturday = readWeeklyTheme({
    themeId: 't1', weekStart: '2026-11-09', title: '테마', intro: '시작', outro: '끝',
    days: [{ day: 'FRI', missionId: 'm5', thinkingType: 'REFLECT', state: 'OPEN', attemptStatus: 'COMPLETED' }],
    review: { open: true, missions: [] },
  })!
  assert.equal(endingDue(saturday), false, '엔딩 전(틀린 뒤 다시 풀기를 아직 안 마침)이면 공책으로')
  const ended = { ...saturday, ending: 'ENDED' as const }
  assert.equal(endingDue(ended), true, '다시 풀기를 마무리해 엔딩이 됨')
  assert.equal(endingDue({ ...ended, introSeen: false }), true, '되돌아보기에서 연 문제는 시작 이야기를 거치지 않음')
  assert.equal(endingDue({ ...ended, outroSeen: true }), false, '이미 본 엔딩은 다시 띄우지 않음')
  assert.equal(endingDue({ ...ended, outro: null }), false, '종료 이야기가 없는 수동 테마')
  const sunday = { ...ended, review: { open: false, missions: [] }, days: ended.days.map((d) => ({ ...d, state: 'CLOSED' as const })) }
  assert.equal(endingDue(sunday), false, '무료 일요일은 새로 띄우지 않음')
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
  assert.deepEqual(post, { postId: 'p1', author: { nickname: '하늘', companion: 'kongi', equipped: { HAT: null, OUTFIT: null, ACCESSORY: null, BACKGROUND: null } }, answer: '까닭', myReactions: ['NEW_IDEA'], createdAt: '' })
  const [mine] = readMyPosts({ items: [{ postId: 'p2', missionTitle: '미션', status: 'HIDDEN_REPORT', reactions: { CLEAR_REASON: 2 } }] })
  assert.equal(mine.status, 'HIDDEN_REPORT')
  assert.deepEqual(mine.reactions, { NEW_IDEA: 0, CLEAR_REASON: 2, DIFFERENT_VIEW: 0, WANT_MORE: 0 })
})

test('#635 친구 생각 작성자 착용은 아이템 키로 읽고, 아이템 목록과 맞춰 그림 주소로 바꾼다(목록에 없는 아이템은 빠짐)', () => {
  const [post] = readCommunityPosts({
    items: [{ postId: 'p1', author: { nickname: '초록콩', look: { companion: 'kongi', equipped: { HAT: 'HAT_GONE', OUTFIT: 'OUTFIT_RAIN', ACCESSORY: '', BACKGROUND: null } } }, answer: '답' }],
  })
  assert.deepEqual(post.author.equipped, { HAT: 'HAT_GONE', OUTFIT: 'OUTFIT_RAIN', ACCESSORY: null, BACKGROUND: null })
  const items = readLookItems({ items: [
    { itemKey: 'OUTFIT_RAIN', slot: 'OUTFIT', name: '노란 비옷', pricePoints: 60, assetKey: 'looks/outfit-rain.svg', unlocked: false, onSale: true },
  ] })
  assert.deepEqual(wornAssets(post.author.equipped, items), { OUTFIT: 'looks/outfit-rain.svg' }, '판매 중단 등으로 목록에 없는 모자는 그리지 않음')
})

test('#710 내 공책 탭: EXTRA만 더 풀어 본 문제, 테마 문제·칸 없음·모르는 값은 테마 문제', () => {
  assert.equal(journalTab({ context: 'EXTRA' }), 'EXTRA')
  assert.equal(journalTab({ context: 'THEME_DAY' }), 'THEME')
  assert.equal(journalTab({ context: 'THEME_REVIEW' }), 'THEME', '주말 되돌아보기 다시 풀기도 테마 문제')
  assert.equal(journalTab({}), 'THEME', '칸이 없는 기록은 사라지지 않게 테마 문제(기준안)')
  assert.deepEqual(['THEME_DAY', 'THEME_REVIEW', 'EXTRA', 'DAILY', '', null].map(isAttemptContext), [true, true, true, false, false, false])
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
  const item = { itemKey: 'HAT_ACORN', slot: 'HAT', name: '도토리 모자', pricePoints: 40, unlocked: false, onSale: true, assetKey: 'looks/hat-acorn.svg', ownedCount: null, createdAt: '2026-11-06T00:00:00Z' }
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

test('#705 꾸미기 목록: 방 소품 보유 개수·등록일을 읽고, 다른 칸 보유 개수는 null, 보유 개수가 틀린 방 소품만 버린다', () => {
  const at = '2026-11-17T00:00:00Z'
  const base = { name: '이름', pricePoints: 30, onSale: true, assetKey: 'room/decor-plant.svg' }
  const items = readLookItems({ items: [
    { ...base, itemKey: 'DECOR_PLANT', slot: 'DECOR', unlocked: true, ownedCount: 3, createdAt: at },
    { ...base, itemKey: 'DECOR_RUG', slot: 'DECOR', unlocked: false, ownedCount: 0, createdAt: at },
    { ...base, itemKey: 'FLOOR_WOOD', slot: 'FLOOR', unlocked: false, ownedCount: 5, createdAt: at },
    { ...base, itemKey: 'THEME:space', slot: 'THEME', assetKey: null, unlocked: false, ownedCount: null, createdAt: null },
    { ...base, itemKey: 'HAT_ACORN', slot: 'HAT', unlocked: false, ownedCount: null, createdAt: '날짜 아님' },
    // 보유 개수를 모르는 방 소품(없음·음수·상한 초과·소수)은 그 항목만 버린다
    { ...base, itemKey: 'DECOR_A', slot: 'DECOR', unlocked: false, createdAt: at },
    { ...base, itemKey: 'DECOR_B', slot: 'DECOR', unlocked: false, ownedCount: -1, createdAt: at },
    { ...base, itemKey: 'DECOR_C', slot: 'DECOR', unlocked: true, ownedCount: DECOR_MAX_OWNED + 1, createdAt: at },
    { ...base, itemKey: 'DECOR_D', slot: 'DECOR', unlocked: true, ownedCount: 1.5, createdAt: at },
  ] })
  assert.deepEqual(items.map((i) => [i.itemKey, i.slot, i.ownedCount, i.createdAt]), [
    ['DECOR_PLANT', 'DECOR', 3, at],
    ['DECOR_RUG', 'DECOR', 0, at],
    ['FLOOR_WOOD', 'FLOOR', null, at],
    ['THEME:space', 'THEME', null, null],
    ['HAT_ACORN', 'HAT', null, null],
  ])
  assert.equal(DECOR_MAX_OWNED, 8)
  assert.equal(SLOT_LABELS.FLOOR, '바닥')
  assert.equal(SLOT_LABELS.DECOR, '방 소품')
  assert.equal(SLOT_LABELS.ACCESSORY, '소품', '캐릭터 착용 칸 소품은 그대로')
  assert.equal(ALL_ITEM_SLOTS.includes('FLOOR') || ALL_ITEM_SLOTS.includes('DECOR'), false, '관리자 칸 선택은 #706에서')
})

test('#705 착용 바닥 칸은 서버가 줄 때만 만들고, 방 소품은 착용 칸이 아니다', () => {
  const look = readLook({ theme: 'lake', companion: 'mungchi', equipped: { HAT: null, OUTFIT: null, ACCESSORY: null, BACKGROUND: null, DESK: null, WALL: null, WARDROBE: null, FLOOR: 'FLOOR_MINT', DECOR: 'DECOR_PLANT' } })
  assert.equal(look.equipped?.FLOOR, 'FLOOR_MINT')
  assert.equal('DECOR' in (look.equipped ?? {}), false)
  assert.equal('FLOOR' in (readLook({ theme: 'lake', companion: 'mungchi', equipped: { HAT: null, DESK: null } }).equipped ?? {}), false)
  assert.equal(readLook({ theme: 'lake', companion: 'mungchi', equipped: { FLOOR: 3 } }).equipped?.FLOOR, null)
  assert.equal(readEquipped({ FLOOR: 'FLOOR_WOOD' }).FLOOR, 'FLOOR_WOOD')
  assert.equal('FLOOR' in readEquipped({ HAT: 'HAT_ACORN' }), false)
})

test('#705 방 소품 사기: 명세 경로·멱등 키로 보내고, 응답의 보유 개수·잔액만 받는다', async (t) => {
  setAccessToken('synthetic-student', 'STUDENT')
  const calls: { url: string; init: RequestInit }[] = []
  let body: unknown = { itemKey: 'DECOR_PLANT', ownedCount: 2, balance: 57 }
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init })
    return Response.json(body)
  })
  assert.deepEqual(await retentionApi.purchaseDecor('DECOR_PLANT', 'key-3'), { itemKey: 'DECOR_PLANT', ownedCount: 2, balance: 57 })
  assert.equal(`${calls[0].init.method} ${calls[0].url}`, 'POST /api/v1/students/me/look-items/DECOR_PLANT/purchase')
  assert.equal(new Headers(calls[0].init.headers).get('Idempotency-Key'), 'key-3')
  assert.equal(calls[0].init.body, undefined)
  assert.equal(calls[0].init.cache, 'no-store')
  for (const bad of [
    { itemKey: 'DECOR_RUG', ownedCount: 2, balance: 57 },
    { itemKey: 'DECOR_PLANT', ownedCount: 0, balance: 57 },
    { itemKey: 'DECOR_PLANT', ownedCount: 9, balance: 57 },
    { itemKey: 'DECOR_PLANT', ownedCount: 2, balance: -1 },
  ]) {
    body = bad
    await assert.rejects(retentionApi.purchaseDecor('DECOR_PLANT', 'key-4'), /확인하지 못/, JSON.stringify(bad))
  }
  assert.deepEqual(readDecorPurchaseResult({ itemKey: 'X', ownedCount: 8, balance: 0 }, 'X'), { itemKey: 'X', ownedCount: 8, balance: 0 })
})

test('#705 멱등 키: 사기마다 새 키, 응답을 못 받으면 같은 키로 다시, 확정 4xx 뒤에는 키를 버린다', () => {
  let n = 0
  const keys = createIdempotencyKeys(() => `key-${++n}`)
  const problem = (status: number, code: string) => new ApiError({ status, code, title: code })
  // 성공하면 다음 사기는 새 키(같은 방 소품을 두 번 사도 두 번째가 첫 응답으로 돌아오지 않게)
  const first = keys.take('DECOR_PLANT')
  keys.settle('DECOR_PLANT', first)
  const second = keys.take('DECOR_PLANT')
  assert.notEqual(second, first)
  // 응답을 못 받음(네트워크 오류)·5xx·처리 중·응답 읽기 실패는 같은 키로 다시
  for (const lost of [new TypeError('Failed to fetch'), problem(503, 'IDEMPOTENCY_UNAVAILABLE'), problem(409, 'IDEMPOTENCY_IN_PROGRESS'), new Error('포인트·꾸미기 정보를 확인하지 못했어요.')]) {
    keys.settle('DECOR_PLANT', second, lost)
    assert.equal(keys.take('DECOR_PLANT'), second, String(lost))
  }
  // 확정 4xx(잔액 부족·판매 중단·보유 상한·없는 항목·키 재사용·방 소품 해금)는 키를 버린다
  for (const code of ['INSUFFICIENT_POINTS', 'LOOK_ITEM_NOT_ON_SALE', 'LOOK_DECOR_LIMIT', 'LOOK_ITEM_NOT_FOUND', 'IDEMPOTENCY_KEY_REUSED', 'VALIDATION_FAILED']) {
    const used = keys.take('THEME:space')
    keys.settle('THEME:space', used, problem(code === 'LOOK_ITEM_NOT_FOUND' ? 404 : code === 'IDEMPOTENCY_KEY_REUSED' || code === 'VALIDATION_FAILED' ? 422 : 409, code))
    assert.equal(keys.peek('THEME:space'), undefined, code)
    assert.notEqual(keys.take('THEME:space'), used, code)
    keys.settle('THEME:space', keys.peek('THEME:space')!)
  }
  // 항목마다 따로, 늦게 끝난 옛 요청은 새 키를 지우지 않는다
  const a = keys.take('A'), b = keys.take('B')
  assert.notEqual(a, b)
  keys.settle('A', 'old-key')
  assert.equal(keys.peek('A'), a)
  assert.equal(keepIdempotencyKey(problem(401, 'SESSION_CHANGED')), true)
  assert.equal(keepIdempotencyKey(problem(500, 'INTERNAL')), true)
  assert.equal(keepIdempotencyKey(problem(400, 'VALIDATION_FAILED')), false)
})

test('#705 방 소품 사기 가능·오류 문구: 판매 중이고 8개 전까지만, 보유 상한은 "더 살 수 없어요"', () => {
  const decor = { itemKey: 'DECOR_PLANT', slot: 'DECOR' as const, name: '화분', pricePoints: 30, unlocked: true, onSale: true, assetKey: 'room/decor-plant.svg', ownedCount: 7, createdAt: null }
  assert.equal(canBuyMore(decor), true)
  assert.equal(canBuyMore({ ...decor, ownedCount: 8 }), false)
  assert.equal(canBuyMore({ ...decor, onSale: false }), false, '판매 중단은 새로 살 수 없음')
  assert.equal(canBuyMore({ ...decor, slot: 'FLOOR', ownedCount: null }), false, '바닥은 해금')
  assert.equal(canBuyMore(undefined), false)
  assert.match(unlockMessage(new ApiError({ status: 409, code: 'LOOK_DECOR_LIMIT', title: '' }))!, /더 살 수 없어요/)
  assert.equal(unlockMessage(new ApiError({ status: 409, code: 'INSUFFICIENT_POINTS', title: '' })), '포인트가 조금 모자라요. 미션을 끝내면 포인트가 쌓여요.')
})

test('#709 친구 방 응답: 그림 키·기본값·액자 순서를 읽고, 학생 ID·회차 키·방 소품은 화면 상태에 두지 않는다', () => {
  const room = readFriendRoom({
    nickname: '하늘별',
    studentId: 'stu-1',
    look: { theme: 'lake', companion: 'tori', equipped: { HAT: 'looks/hat-acorn.svg', OUTFIT: null, ACCESSORY: '' } },
    room: {
      wallpaper: 'room/wall-sky.svg', floor: null,
      furniture: { DESK: 'room/desk-cherry.svg', WALL: null, WARDROBE: 'room/wardrobe-berry.svg' },
      decor: [{ spotNo: 1, assetKey: 'room/decor-plant.svg' }],
      frames: [
        { slotNo: 3, title: '별빛 우체국', imageUrl: '/demo/album/past-post.jpg', themeId: 'th-1', weekStart: '2026-11-02' },
        { slotNo: 1, title: '잃어버린 지도 조각', imageUrl: '' },
      ],
    },
  })
  assert.deepEqual(room, {
    nickname: '하늘별',
    companion: 'tori',
    worn: { HAT: 'looks/hat-acorn.svg' },
    room: { wallpaper: 'room/wall-sky.svg', floor: null, desk: 'room/desk-cherry.svg', wall: null, wardrobe: 'room/wardrobe-berry.svg' },
    frames: [
      { slotNo: 1, title: '잃어버린 지도 조각', imageUrl: null },
      { slotNo: 3, title: '별빛 우체국', imageUrl: '/demo/album/past-post.jpg' },
    ],
  })
  // 모르는 캐릭터는 기본 캐릭터, 빈 별명은 "친구"
  assert.equal(readFriendRoom({ nickname: '', look: { companion: 'nope', equipped: {} }, room: { furniture: {}, frames: [] } }).companion, 'mungchi')
  assert.equal(readFriendRoom({ nickname: '', look: { equipped: {} }, room: { furniture: {}, frames: [] } }).nickname, '친구')
})

test('#709 친구 방 응답 모양이 틀리면 계약 오류(화면은 공통 오류·다시 시도)', () => {
  const ok = { nickname: '초록콩', look: { companion: 'kongi', equipped: {} }, room: { furniture: {}, frames: [] } }
  assert.doesNotThrow(() => readFriendRoom(ok))
  for (const bad of [
    null,
    { ...ok, nickname: 3 },
    { ...ok, look: undefined },
    { ...ok, room: { ...ok.room, frames: 'x' } },
    { ...ok, room: { ...ok.room, wallpaper: 7 } },
    { ...ok, look: { equipped: { HAT: 1 } } },
    { ...ok, room: { ...ok.room, frames: [{ slotNo: 7, title: 'a' }] } },
    { ...ok, room: { ...ok.room, frames: [{ slotNo: 1, title: 'a' }, { slotNo: 1, title: 'b' }] } },
    { ...ok, room: { ...ok.room, frames: [{ slotNo: 1 }] } },
  ]) assert.throws(() => readFriendRoom(bad), /친구 방 정보를 확인하지 못했어요/)
})
