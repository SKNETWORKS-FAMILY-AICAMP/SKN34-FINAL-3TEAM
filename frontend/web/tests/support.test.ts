import test from 'node:test'
import assert from 'node:assert/strict'
import { adminApi } from '../src/data/admin/api.ts'
import { correctionImpactText } from '../src/domain/admin/operations.ts'
import { setAccessToken } from '../src/data/apiClient.ts'

test('정정 재시도는 동일한 Idempotency-Key와 enum 결과를 전달한다', async () => {
  const original = globalThis.fetch
  const requests: RequestInit[] = []
  setAccessToken('support-token', 'ADMIN')
  globalThis.fetch = async (_input, init) => {
    requests.push(init!)
    return new Response(JSON.stringify({ reportId: 'r', status: 'RESOLVED', corrections: [] }), { headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const key = crypto.randomUUID()
    await adminApi.correction('r', '근거 확인', 'CORRECT', key)
    await adminApi.correction('r', '근거 확인', 'CORRECT', key)
    for (const req of requests) {
      assert.equal(new Headers(req.headers).get('Idempotency-Key'), key)
      assert.deepEqual(JSON.parse(req.body as string), { reason: '근거 확인', corrected: 'CORRECT' })
    }
  } finally { globalThis.fetch = original; setAccessToken(null) }
})


test('파생 결과가 모두 UNKNOWN이어도 전체 반영 완료라고 표시하지 않는다', () => {
  const text = correctionImpactText({ conversation: 'UNKNOWN', aggregation: 'UNKNOWN', report: 'UNKNOWN' })
  assert.equal(text.split('반영 여부 미확인').length - 1, 3)
  assert.ok(text.includes('학습 수치 집계'))
  assert.ok(!text.includes('반영 확인'))
  assert.ok(!text.includes('모두 반영'))
})

test('집계 NOT_APPLIED는 변경 대상 없음도 포함하며 오류나 재생성 필요로 표시하지 않는다', () => {
  const text = correctionImpactText({ conversation: 'UNKNOWN', aggregation: 'NOT_APPLIED', report: 'APPLIED' })
  assert.ok(text.includes('학습 수치 집계: 미반영 확인'))
  assert.ok(text.includes('변경 대상 없음 포함'))
  assert.ok(text.includes('오류·후속 처리 필요 아님'))
  assert.ok(text.includes('리포트: 반영 확인'))
  assert.ok(!text.includes('재생성 필요'))
  assert.ok(!text.includes('처리 실패'))
})

test('반영 정보가 없거나 형식이 잘못된 경우 성공으로 대체하지 않는다', () => {
  assert.equal(correctionImpactText(null), '파생 결과 반영 정보 없음')
  assert.equal(correctionImpactText({ aggregation: 'FAILED' }), '반영 정보의 형식을 확인할 수 없습니다.')
  assert.equal(correctionImpactText('확인 대기(목업)'), '이전 형식의 반영 정보: 확인 대기(목업)')
})

test('정정의 공개 409·422는 refresh나 성공 대체 없이 소비자 오류로 유지한다', async () => {
  const original = globalThis.fetch
  setAccessToken('support-token', 'ADMIN')
  try {
    for (const [status, code] of [[409, 'SUPPORT_CORRECTION_CONFLICT'], [422, 'SUPPORT_CORRECTION_REJECTED']] as const) {
      let calls = 0
      globalThis.fetch = async () => {
        calls++
        return new Response(JSON.stringify({ status, code, title: '정정 요청 거부' }), { status, headers: { 'Content-Type': 'application/problem+json' } })
      }
      await assert.rejects(adminApi.correction('r', '근거 확인', 'CORRECT', crypto.randomUUID()), (error: unknown) => {
        const problem = (error as { problem: { status: number; code: string } }).problem
        assert.equal(problem.status, status); assert.equal(problem.code, code)
        return true
      })
      assert.equal(calls, 1)
    }
  } finally { globalThis.fetch = original; setAccessToken(null) }
})
