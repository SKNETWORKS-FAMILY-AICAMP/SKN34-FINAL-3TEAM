import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatKoreanDateTime } from '../src/presentation/common/dateTime.ts'

test('UTC 시각을 한국 날짜로 넘기고 초·밀리초·ISO 기호를 노출하지 않는다', () => {
  assert.equal(formatKoreanDateTime('2026-11-18T02:23:55.698Z'), '2026년 11월 18일 11:23')
  assert.equal(formatKoreanDateTime('2026-11-18T15:01:59Z'), '2026년 11월 19일 00:01')
  assert.equal(formatKoreanDateTime('2026-11-19T00:01:59+09:00'), '2026년 11월 19일 00:01')
})

test('시각 없음과 해석할 수 없는 시각을 구분한다', () => {
  assert.equal(formatKoreanDateTime(null), '—')
  assert.equal(formatKoreanDateTime(''), '—')
  assert.equal(formatKoreanDateTime('invalid-date'), '시각 확인 불가')
})
