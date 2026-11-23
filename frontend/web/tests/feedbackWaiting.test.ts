import test from 'node:test'
import assert from 'node:assert/strict'
import {
  FEEDBACK_WAIT_LIMIT_SECONDS,
  WAITING_STEPS,
  resumeWaitStart,
  waitingStep,
} from '../src/presentation/student/world/missionSteps.ts'

// #847 피드백 대기 표시: 경과 초 → 문구·움직임(실제 진행과 무관한 시간표)
test('대기 단계 경계: 0·5·15·30·60초에 문구가 바뀌고 움직임은 단계마다 하나', () => {
  const at = (s: number) => waitingStep(s)
  assert.deepEqual([0, 4.99, 5, 14.99, 15, 29.99, 30, 59.99, 60, 80].map((s) => at(s).index), [0, 0, 1, 1, 2, 2, 3, 3, 4, 4])
  assert.equal(at(0).line, '답을 꼼꼼히 읽고 있어')
  assert.equal(at(5).line, '생각의 단서를 찾는 중이야')
  assert.equal(at(15).line, '너에게 할 질문을 고르고 있어')
  assert.equal(at(30).line, '조금 오래 걸리네. 답은 벌써 저장했어!')
  assert.equal(at(60).line, '거의 다 왔어. 잠깐만 기다려 줘')
  assert.deepEqual([0, 5, 15, 30, 60].map((s) => at(s).motion), ['look', 'notebook', 'tilt', 'stretch', 'stretch'])
  assert.equal(WAITING_STEPS.length, 5)
})

test('다음 단계까지 남은 초: 경계에서만 깨우도록 계산, 마지막 단계는 null', () => {
  assert.equal(waitingStep(0).next, 5)
  assert.equal(waitingStep(3).next, 2)
  assert.equal(waitingStep(29.5).next, 0.5)
  assert.equal(waitingStep(60).next, null)
  assert.equal(waitingStep(80).next, null)
})

test('음수·80초 넘음·NaN은 0~80초로 자른다', () => {
  assert.equal(waitingStep(-12).index, 0)
  assert.equal(waitingStep(-12).next, 5)
  assert.equal(waitingStep(500).index, 4)
  assert.equal(waitingStep(Number.NaN).index, 0)
  assert.equal(waitingStep(Number.POSITIVE_INFINITY).index, 4)
  assert.equal(FEEDBACK_WAIT_LIMIT_SECONDS, 80)
})

test('이어받기 시작 시각: 마지막 답 submittedAt부터, 기기 시계 오차는 0~80초로 자름', () => {
  const now = Date.parse('2026-11-23T10:00:00+09:00')
  // 20초 전에 보낸 답 → 20초 지난 것으로
  assert.equal(resumeWaitStart('2026-11-23T09:59:40+09:00', now), now - 20_000)
  // 서버 시각이 기기보다 앞서 미래로 보이면 지금부터
  assert.equal(resumeWaitStart('2026-11-23T10:00:30+09:00', now), now)
  // 아주 오래전(기기 시계가 늦음 등)이면 80초 전까지만
  assert.equal(resumeWaitStart('2026-11-23T09:00:00+09:00', now), now - 80_000)
  // 없거나 읽을 수 없으면 지금부터
  assert.equal(resumeWaitStart(undefined, now), now)
  assert.equal(resumeWaitStart('어제', now), now)
  assert.equal(waitingStep((now - resumeWaitStart('2026-11-23T09:59:40+09:00', now)) / 1000).line, '너에게 할 질문을 고르고 있어')
})
