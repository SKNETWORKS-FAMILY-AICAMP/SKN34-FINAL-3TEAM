import test from 'node:test'
import assert from 'node:assert/strict'
import {
  EDITABLE_GRADES,
  REGISTRATION_GRADES,
  gradeLabel,
  isStoredGrade,
} from '../src/domain/grade.ts'
import { notificationLabels, notificationPath } from '../src/domain/service.ts'

test('학년은 초3~중3까지 저장하고 등록은 초3~6만 고른다 (#432)', () => {
  assert.deepEqual(
    EDITABLE_GRADES.map(gradeLabel),
    ['초등 3학년', '초등 4학년', '초등 5학년', '초등 6학년', '중학교 1학년', '중학교 2학년', '중학교 3학년'],
  )
  assert.deepEqual([...REGISTRATION_GRADES], [3, 4, 5, 6])
  assert.deepEqual([2, 3, 9, 10, 4.5, '5'].map(isStoredGrade), [false, true, true, false, false, false])
})

test('학년 진급 알림은 설정에 보이고 정보 관리로 연결된다 (#432)', () => {
  assert.equal(notificationLabels.GRADE_PROMOTED, '학년 진급')
  assert.equal(Object.keys(notificationLabels).length, 9)
  assert.equal(notificationPath('/parent/settings', 'PARENT', 'https://app.test'), '/parent/settings')
})
