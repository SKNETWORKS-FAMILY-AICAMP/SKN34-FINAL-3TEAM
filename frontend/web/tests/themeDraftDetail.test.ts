import test from 'node:test'
import assert from 'node:assert/strict'
import { themeDraftActions, themeDraftOf } from '../src/domain/admin/themeDrafts.ts'
import { captionAt, readThemeMotion } from '../src/domain/themeMotion.ts'

// #441 테마 초안 상세·움직임 형식 v1 읽기. 가상 값만 쓴다.
const base = { draftId: 'd-1', status: 'READY' }

test('테마 초안 상세: 계약 칸을 읽고 모르는 값·빠진 칸은 비운 값으로 둔다', () => {
  const d = themeDraftOf({
    ...base, source: 'AUTO', grade: 'G4', weekStart: '2026-11-16', attempts: 2, maxAttempts: 3,
    input: { topic: '종', missions: [{ thinkingType: 'ANALYZE', inputType: 'NARRATIVE', standardCodes: ['4과03-01'] }, { thinkingType: 'X', inputType: 'Y', standardCodes: 'no' }] },
    checkResults: [{ attempt: 1, failures: [{ stage: 'LEARNING', reasons: ['WED QUESTION_LENGTH 김'] }] }],
    draft: {
      theme: { title: '사라진 종', intro: '시작', outro: '끝', bigQuestion: '어디?', candidates: ['시계탑', 3], answer: '시계탑',
        days: [{ day: 'MON', thinkingType: 'ANALYZE', place: '광장', clue: '단서', rulesOut: ['빵집'] }, { day: 'SUN' }] },
      missions: [{ day: 'MON', thinkingType: 'ANALYZE', draft: { title: '월', question: '무엇을 봤나요?', guide: null } }],
      dialogues: [{ day: 'MON', lines: [{ speaker: '뭉치', text: '여기!' }, { speaker: 1 }] }],
      warnings: [{ stage: 'VIDEO', item: 'ALL', reason: '영상 없음' }],
    },
    scenes: [{ scene: 'INTRO', imageUrl: 'https://img', videoUrl: null, motion: { version: 1 } }, { scene: 'BAD', imageUrl: 'x' }],
    failureCode: null, versions: { prompt: 'p@1', model: 'm' }, themeId: null, createdAt: '2026-11-12T00:00:00Z',
  })
  assert.equal(d.source, 'AUTO')
  assert.equal(d.grade, 'G4')
  assert.equal(d.input.missions[1].thinkingType, null)
  assert.deepEqual(d.input.missions[1].standardCodes, [])
  assert.equal(d.checkResults[0].failures[0].stage, 'LEARNING')
  assert.deepEqual(d.draft?.theme?.candidates, ['시계탑'])
  assert.deepEqual(d.draft?.theme?.days.map((x) => x.day), ['MON'])
  assert.equal(d.draft?.dialogues[0].lines.length, 1)
  assert.deepEqual(d.scenes.map((s) => s.scene), ['INTRO'])
})

test('테마 초안: draftId·status가 없거나 모르는 상태면 오류, 상세가 비어도 상태는 읽는다', () => {
  assert.throws(() => themeDraftOf({ draftId: 'd', status: 'NOPE' }))
  assert.throws(() => themeDraftOf({ status: 'READY' }))
  const bare = themeDraftOf({ draftId: 'd', status: 'GENERATING' })
  assert.equal(bare.draft, null)
  assert.deepEqual(bare.scenes, [])
})

test('상태별 동작: 채택은 READY만, 버리기는 READY·검사 실패·실패, 다시 생성은 생성 중·채택 외', () => {
  assert.deepEqual(themeDraftActions('READY'), { adopt: true, discard: true, regenerate: true })
  assert.deepEqual(themeDraftActions('CHECK_FAILED'), { adopt: false, discard: true, regenerate: true })
  assert.deepEqual(themeDraftActions('GENERATING'), { adopt: false, discard: false, regenerate: false })
  assert.deepEqual(themeDraftActions('ADOPTED'), { adopt: false, discard: false, regenerate: false })
  assert.deepEqual(themeDraftActions('DISCARDED'), { adopt: false, discard: false, regenerate: true })
})

test('움직임 v1: 형식이 다르면 null, 좌표·확대는 범위 안으로, 잘못된 문구·지점은 버림', () => {
  assert.equal(readThemeMotion(null), null)
  assert.equal(readThemeMotion({ version: 2 }), null)
  const m = readThemeMotion({
    version: 1, transition: { kind: 'fade', seconds: 0.5 },
    camera: { from: { x: -10, y: 50, zoom: 1 }, to: { x: 40, y: 60, zoom: 9 }, seconds: 6 },
    speakers: { 뭉치: { x: 39, y: 69, zoom: 1.2 }, 빈: {} },
    effects: [{ shape: 'circle', color: '#fff', count: 99 }, { color: 'red' }],
    captions: [{ start: 3, end: 6, text: '둘' }, { start: 0, end: 3, text: '하나' }, { start: 5, end: 4, text: '거꾸로' }],
    spots: [{ x: 25, y: 70, label: '발자국', line: '어디로?', evidence: true }, { x: 10, y: 10 }],
  })!
  assert.deepEqual(m.camera?.from, { x: 0, y: 50, zoom: 1 })
  assert.equal(m.camera?.to.zoom, 4)
  assert.deepEqual(Object.keys(m.speakers), ['뭉치'])
  assert.equal(m.effects.length, 1)
  assert.equal(m.effects[0].count, 40)
  assert.deepEqual(m.captions.map((c) => c.text), ['하나', '둘'])
  assert.equal(m.spots.length, 1)
  assert.equal(captionAt(m, 1), '하나')
  assert.equal(captionAt(m, 4), '둘')
  assert.equal(captionAt(m, 7), null)
})
