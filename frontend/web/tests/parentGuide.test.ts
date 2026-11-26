import test from 'node:test'
import assert from 'node:assert/strict'
import { isParentGuideReplay, PARENT_GUIDE_DEVICES, parentGuidePlace, parentGuideReplayState, parentGuideSteps } from '../src/presentation/parent/parentGuide.ts'

test('학부모 안내 3단계: 기기·PIN → 학습 현황·리포트 → 계정·자녀 설정, 문구는 제안 5.1 초안', () => {
  assert.deepEqual(parentGuideSteps.map(s => s.targets), [['/parent/devices'], ['/parent/journal', '/parent/report'], ['/parent/settings']])
  assert.equal(parentGuideSteps[0].body, '아이가 학습할 기기를 먼저 등록해 주세요. QR을 찍고 PIN을 정하면 아이가 바로 시작할 수 있습니다.')
  assert.equal(parentGuideSteps[1].body, '아이가 푼 문제와 답은 학습 현황에서, 일일·주간 리포트와 AI 챗봇 질문은 리포트에서 봅니다.')
  assert.equal(parentGuideSteps[2].body, '친구들과 답을 나누려면 여기서 공개에 동의해 주세요. 공개는 아이가 직접 켭니다.')
  // 문구 1~2줄: 한 단계 본문은 두 문장 이하
  for (const step of parentGuideSteps) assert.ok(step.body.split('. ').length <= 2, step.title)
  assert.equal(PARENT_GUIDE_DEVICES, '/parent/devices')
})

test('강조 메뉴 위치 문구: 왼쪽 메뉴·하단 바(짧은 이름)·접힌 메뉴', () => {
  assert.equal(parentGuidePlace(['/parent/devices'], 'side'), "왼쪽 메뉴의 '기기·PIN'입니다.")
  assert.equal(parentGuidePlace(['/parent/journal', '/parent/report'], 'bottom'), "화면 아래 메뉴의 '학습'·'리포트'입니다.")
  assert.equal(parentGuidePlace(['/parent/settings'], 'collapsed'), "화면 위 '메뉴'를 열면 '계정·자녀 설정'이 있어요.")
})

test('다시 보기 이동 상태만 재생으로 읽는다', () => {
  assert.equal(isParentGuideReplay(parentGuideReplayState), true)
  assert.equal(isParentGuideReplay(null), false)
  assert.equal(isParentGuideReplay({ parentGuide: 'other' }), false)
  assert.equal(isParentGuideReplay('replay'), false)
})
