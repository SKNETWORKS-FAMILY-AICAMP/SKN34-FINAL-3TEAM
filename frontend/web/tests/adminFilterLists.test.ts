// #655 관리자 사용량·감사 기록 필터 목록은 서버 값 전체여야 한다
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { auditTargetLabels, callTypeLabels, labelOf } from '../src/domain/admin/operations.ts'
import { auditActionLabel } from '../src/presentation/admin/adminFormatting.ts'

const root = new URL('../../../', import.meta.url)
const read = (path: string) => readFileSync(new URL(path, root), 'utf-8')

test('호출 종류 필터는 core CallType·OpenAPI CallType과 같은 값·순서', () => {
  const kotlin = read('backend/core-service/src/main/kotlin/com/sagomungchi/core/usage/domain/UsageSummary.kt')
  const core = kotlin.match(/enum class CallType \{([^}]*)\}/)![1].split(',').map(v => v.trim())
  assert.deepEqual(Object.keys(callTypeLabels), core)
  const openapi = read('contracts/openapi/core-service.yaml')
  const block = openapi.slice(openapi.indexOf('    CallType:'))
  const values = block.match(/enum: \[([^\]]*)\]/)![1].split(',').map(v => v.trim())
  assert.deepEqual(Object.keys(callTypeLabels), values)
})

test('감사 대상 유형 필터는 core가 audit_log에 고정 값으로 쓰는 유형을 모두 담는다', () => {
  const sources = [
    'backend/core-service/src/main/resources/mybatis/account/AccountManagementMapper.xml',
    'backend/core-service/src/main/resources/mybatis/admin/ConversationRetryAuditMapper.xml',
    'backend/core-service/src/main/resources/mybatis/admin/ModelVersionMapper.xml',
    'backend/core-service/src/main/resources/mybatis/admin/OperationsMapper.xml',
    'backend/core-service/src/main/resources/mybatis/payment/PaymentMapper.xml',
    'backend/core-service/src/main/resources/mybatis/reward/RewardMapper.xml',
  ].map(read).join('\n')
  const fixed = [...sources.matchAll(/INSERT INTO audit_log\([^)]*target_type[^)]*\)\s*VALUES\(([^)]*)\)/gi)]
    .flatMap(m => [...m[1].matchAll(/'([A-Z_]+)'/g)].map(v => v[1]))
    .filter(v => !['SUCCESS', 'FAILURE', 'JOB_RETRY'].includes(v) && !v.endsWith('_UPDATED') && !v.endsWith('_CREATED'))
  const service = read('backend/core-service/src/main/kotlin/com/sagomungchi/core/support/service/SupportService.kt')
  const support = [...service.matchAll(/repository\.audit\([^,]+,[^,]+,"([A-Z_]+)"/g)].map(m => m[1])
  const missions = read('backend/core-service/src/main/kotlin/com/sagomungchi/core/admin/service/MissionAuditService.kt')
  const mission = [...missions.matchAll(/const val [A-Z_]+ *= *"([A-Z_]+)"/g)].map(m => m[1])
  for (const value of new Set([...fixed, ...support, ...mission, 'CONVERSATION', 'REPORT', 'NOTIFICATION']))
    assert.ok(value in auditTargetLabels, value)
})

test('표현 검토 감사는 대상 유형 필터와 작업 이름표에 core가 쓰는 값 그대로 있다 (#907)', () => {
  const service = read('backend/core-service/src/main/kotlin/com/sagomungchi/core/admin/service/ExpressionReviewAuditService.kt')
  const value = (name: string) => service.match(new RegExp(`const val ${name} = "([A-Z_]+)"`))![1]
  assert.equal(labelOf(auditTargetLabels, value('TARGET_TYPE')), '표현 검토')
  assert.equal(auditActionLabel(value('VIEW')), '표현 검토 목록 열람')
  assert.equal(auditActionLabel(value('LABEL')), '표현 검토 라벨')
})

test('목록에 없는 값은 원래 값 그대로 보인다', () => {
  assert.equal(labelOf(callTypeLabels, 'M2'), '서술 채점 모델(M2)')
  assert.equal(labelOf(auditTargetLabels, 'NEW_TARGET'), 'NEW_TARGET')
})
