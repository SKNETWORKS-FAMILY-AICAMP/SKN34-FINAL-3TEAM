import test from 'node:test'
import assert from 'node:assert/strict'
import { difficultyText } from '../src/domain/parent.ts'

test('학부모 리포트 돌아보기 난이도는 report와 같은 문구, 모르는 값은 그대로 (#860)', () => {
  assert.equal(difficultyText('EASY'), '쉬웠어요')
  assert.equal(difficultyText('NORMAL'), '보통')
  assert.equal(difficultyText('HARD'), '어려웠어요')
  // report 주간 응답은 이미 문구로 바꿔서 온다
  assert.equal(difficultyText('보통'), '보통')
  assert.equal(difficultyText('UNKNOWN'), 'UNKNOWN')
  assert.equal(difficultyText('toString'), 'toString')
  assert.equal(difficultyText(null), '')
  assert.equal(difficultyText(undefined), '')
})
