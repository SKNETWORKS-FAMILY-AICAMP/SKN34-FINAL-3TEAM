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

// #440: 예전에는 범위 밖 값을 잘라 맞추고 방향을 글자('up'·'down'), 확대를 1~4로 읽었다. 학생 이야기 화면(retention.ts)과 같은
// 한 함수로 합치면서 ai 계약(ThemeMotion v1) 범위를 하나라도 벗어나면 그림만(null)으로 바꿈(이슈 #440 "형식이 틀리면 그림만")
test('움직임 v1: 형식이 다르거나 범위를 벗어나면 null(그림만), 문구는 시작 순으로 읽고 시각에 맞는 문구를 고른다', () => {
  assert.equal(readThemeMotion(null), null)
  assert.equal(readThemeMotion({ version: 2 }), null)
  const ok = {
    version: 1, transition: { kind: 'fade', seconds: 0.5 },
    camera: { from: { x: 0, y: 50, zoom: 1 }, to: { x: 40, y: 60, zoom: 1.4 }, seconds: 8 },
    speakers: { 뭉치: { x: 39, y: 69, zoom: 1.2 } },
    effects: [{ shape: 'circle', color: '#FFFFFF', count: 20, size: 6, direction: 359, speed: 20, opacity: 0.8 }],
    captions: [{ start: 3, end: 6, text: '둘' }, { start: 0, end: 3, text: '하나' }],
    spots: [{ x: 25, y: 70, label: '발자국', line: '어디로?', evidence: true }],
  }
  const m = readThemeMotion(ok)!
  assert.deepEqual(m.camera?.to, { x: 40, y: 60, zoom: 1.4 })
  assert.deepEqual(m.captions.map((c) => c.text), ['하나', '둘'])
  assert.equal(m.spots.length, 1)
  assert.equal(captionAt(m, 1), '하나')
  assert.equal(captionAt(m, 4), '둘')
  assert.equal(captionAt(m, 7), null)
  for (const bad of [
    { ...ok, camera: { ...ok.camera, from: { x: -10, y: 50, zoom: 1 } } },
    { ...ok, camera: { ...ok.camera, to: { x: 40, y: 60, zoom: 4 } } },
    { ...ok, speakers: { 뭉치: { x: 39, y: 69, zoom: 1.2 }, 빈: {} } },
    { ...ok, effects: [{ ...ok.effects[0], count: 99 }] },
    { ...ok, effects: [{ ...ok.effects[0], color: '#fff' }] },
    { ...ok, captions: [{ start: 5, end: 4, text: '거꾸로' }] },
    { ...ok, spots: [{ x: 10, y: 10 }] },
  ]) assert.equal(readThemeMotion(bad), null, JSON.stringify(bad).slice(0, 80))
})
