import test from 'node:test'
import assert from 'node:assert/strict'
import { islands, missionStage, readLook, todayMission } from '../src/domain/studentLook.ts'
import type { Mission } from '../src/domain/classroom.ts'

const m = (id: string, thinkingType: Mission['thinkingType'], status: Mission['status']) =>
  ({ id, title: id, subject: '과학', grade: 3, thinkingType, inputType: 'NARRATIVE', question: '', hint: '', scene: 'science', status }) as Mission

test('꾸미기 설정: 알 수 없는 값은 기본값으로', () => {
  assert.deepEqual(readLook({ theme: 'forest', companion: 'tori', updatedAt: 'x' }), {
    theme: 'forest',
    companion: 'tori',
    updatedAt: 'x',
  })
  assert.deepEqual(readLook({ theme: 'mars', companion: 'dragon' }), {
    theme: 'lake',
    companion: 'mungchi',
    updatedAt: null,
  })
  assert.equal(readLook(null).theme, 'lake')
})

test('오늘의 미션: 이어할 시도 → 진행 중 → 시작 전 순서, 모두 끝났으면 없음', () => {
  const missions = [m('a', 'ANALYZE', 'COMPLETED'), m('b', 'EVALUATE', 'NOT_STARTED'), m('c', 'SOLVE', 'IN_PROGRESS')]
  assert.equal(todayMission({ resume: null, missions })?.id, 'c')
  assert.equal(todayMission({ resume: null, missions: missions.slice(0, 2) })?.id, 'b')
  assert.equal(todayMission({ resume: null, missions: missions.slice(0, 1) }), null)
})

test('생각 지도: 다섯 곳 모두 표시하고 끝낸 미션 수만 센다', () => {
  const places = islands({
    resume: null,
    missions: [m('a', 'ANALYZE', 'COMPLETED'), m('b', 'ANALYZE', 'COMPLETED'), m('c', 'CREATE', 'NOT_STARTED')],
  })
  assert.deepEqual(places.map((p) => p.type), ['ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT'])
  assert.equal(places[0].done, 2)
  assert.equal(places[2].open, 1)
  assert.deepEqual(places.filter((p) => p.today).map((p) => p.type), ['CREATE'])
  assert.equal(places[1].done, 0, '기록 없는 유형도 0으로 보이고 숨기지 않는다')
})

test('미션 단계: 쓰기 → 한 걸음 더 → 돌아보기', () => {
  assert.equal(missionStage({ answers: [] }), 'write')
  assert.equal(missionStage({ answers: [{} as never] }), 'more')
  assert.equal(missionStage({ answers: [{} as never], finishedAt: '2026-10-27' }), 'reflect')
})
