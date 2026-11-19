import test from 'node:test'
import assert from 'node:assert/strict'
import { blankAnswer } from '../src/domain/classroom.ts'
import { attemptStarted, readThemeScene } from '../src/domain/themeScene.ts'

// #807 오늘 장면: 시도 응답 themeScene 읽기와 "이미 답을 쓴 시도" 판단

test('themeScene: 대화와 관리자 요일 영상을 읽고 hintSpots는 쓰지 않는다', () => {
  const scene = readThemeScene({
    dialogue: [{ speaker: '뭉치', text: '받침대 위에 작은 바퀴 자국이 남았어!' }, { speaker: '아린', text: '같이 볼래?' }],
    hintSpots: [{ seq: 1, x: 10, y: 20 }],
    videoUrl: 'https://cdn.example.test/v.mp4',
  })
  assert.deepEqual(scene, {
    dialogue: [{ speaker: '뭉치', text: '받침대 위에 작은 바퀴 자국이 남았어!' }, { speaker: '아린', text: '같이 볼래?' }],
    videoUrl: 'https://cdn.example.test/v.mp4',
  })
})

test('themeScene: 없거나(EXTRA) 객체가 아니면 null, 대화가 null이면 빈 배열', () => {
  assert.equal(readThemeScene(null), null)
  assert.equal(readThemeScene(undefined), null)
  assert.equal(readThemeScene('scene'), null)
  assert.equal(readThemeScene([]), null)
  assert.deepEqual(readThemeScene({ dialogue: null, hintSpots: null, videoUrl: null }), { dialogue: [], videoUrl: null })
})

test('themeScene: 화자·대사가 빈 줄은 빼고 앞뒤 공백은 지운다(그 줄만 못 보여 줄 뿐 문제는 풀 수 있게)', () => {
  const scene = readThemeScene({
    dialogue: [{ speaker: ' 뭉치 ', text: ' 찾았어 ' }, { speaker: '', text: '이름 없음' }, { speaker: '아린', text: '  ' }, 'x', { speaker: 3, text: '숫자' }],
    videoUrl: '',
  })
  assert.deepEqual(scene, { dialogue: [{ speaker: '뭉치', text: '찾았어' }], videoUrl: null })
})

test('이미 답을 쓴 시도: 보낸 답이 있거나 초안에 글·고른 것이 있으면 true, 빈 초안이면 false', () => {
  const draft = (answer: ReturnType<typeof blankAnswer>) => ({ answer, memo: '', version: '1' })
  assert.equal(attemptStarted({ answers: [], draft: undefined }), false)
  assert.equal(attemptStarted({ answers: [], draft: draft(blankAnswer('NARRATIVE')) }), false)
  assert.equal(attemptStarted({ answers: [], draft: draft({ ...blankAnswer('NARRATIVE'), text: '  ' }) }), false)
  assert.equal(attemptStarted({ answers: [], draft: draft({ ...blankAnswer('NARRATIVE'), text: '내 생각' }) }), true)
  assert.equal(attemptStarted({ answers: [], draft: draft({ ...blankAnswer('SOLUTION_STEPS'), steps: ['', '1250+850'] }) }), true)
  assert.equal(attemptStarted({ answers: [], draft: draft({ ...blankAnswer('SOLUTION_STEPS'), finalAnswer: '1400' }) }), true)
  const essay = blankAnswer('ESSAY')
  assert.equal(attemptStarted({ answers: [], draft: draft({ ...essay, essay: { ...essay.essay, reasons: ['', '둘째'] } }) }), true)
  assert.equal(attemptStarted({ answers: [], draft: draft({ ...blankAnswer('CHOICE'), choiceIds: ['a'] }) }), true)
  assert.equal(attemptStarted({ answers: [], draft: draft({ ...blankAnswer('CLASSIFICATION'), assignments: [{ choiceId: 'a', categoryId: 'g' }] }) }), true)
  assert.equal(attemptStarted({ answers: [{} as never], draft: draft(blankAnswer('NARRATIVE')) }), true)
})
