import test from 'node:test'
import assert from 'node:assert/strict'
import { accountActionLabel, accountEffectText, metricSourceLabel, parentMenuSearch } from '../src/presentation/common/parentDisplay.ts'
import { supportCategoryLabel, supportStatusLabel, supportTargetLabel } from '../src/presentation/support/supportLabels.ts'
import { formatKoreanDateTime } from '../src/presentation/common/dateTime.ts'

test('API 내부 코드는 표시명으로 변환하고 알 수 없는 값은 그대로 노출하지 않는다', () => {
  assert.equal(metricSourceLabel('RECORD'), '학습 기록')
  assert.equal(accountActionLabel('RECORDS'), '학습 기록 삭제')
  for (const code of ['INTERNAL_NEW_STATE', '<script>', '']) {
    assert.equal(metricSourceLabel(code), '출처 확인 필요')
    assert.equal(accountActionLabel(code), '처리 범위 확인 필요')
    assert.equal(supportStatusLabel(code), '처리 상태 확인 필요')
    assert.equal(supportCategoryLabel(code), '문의·신고')
    assert.equal(supportTargetLabel(code), '학습 결과')
  }
})

test('삭제 안내에서 개발 문구만 치환하고 보존 범위와 재개 제한은 유지한다', () => {
  const original = '프로필 보존, 학습·대화·리포트 삭제, 학습 재개는 후속 계약 필요'
  const displayed = accountEffectText(original)
  assert.ok(displayed.startsWith('프로필 보존, 학습·대화·리포트 삭제,'))
  assert.ok(displayed.includes('아직 지원하지 않습니다'))
  assert.ok(!displayed.includes('계약'))
  assert.equal(accountEffectText('프로필·학습·대화·리포트 삭제, 거래 기록 5년 보관'), '프로필·학습·대화·리포트 삭제, 거래 기록 5년 보관')
})

test('동일한 API 시각은 UTC나 한국 시각 표기와 무관하게 같은 날짜로 표시한다', () => {
  assert.equal(formatKoreanDateTime('2026-11-16T23:30:00Z'), formatKoreanDateTime('2026-11-17T08:30:00+09:00'))
  assert.match(formatKoreanDateTime('2026-11-16T23:30:00Z'), /11월 17일/)
  assert.equal(formatKoreanDateTime('invalid'), '시각 확인 불가')
})

test('메뉴 이동 시 이전 신고 대상과 결제·상세 상태를 제거하고 자녀와 기간만 유지한다', () => {
  const search = '?targetId=old-report&targetType=REPORT&reportId=old-report&childId=child-2&from=2026-11-14&to=2026-11-20&section=account&view=chat&checkout=1'
  assert.equal(parentMenuSearch(search), '?childId=child-2&from=2026-11-14&to=2026-11-20')
  assert.equal(parentMenuSearch('?targetId=old-report'), '')
})
