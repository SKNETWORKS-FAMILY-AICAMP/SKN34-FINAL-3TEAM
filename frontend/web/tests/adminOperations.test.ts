import test from 'node:test'
import assert from 'node:assert/strict'
import { adminApi } from '../src/data/admin/api.ts'
import { readFileSync } from 'node:fs'
import { getResponse } from 'msw'
import { usageGroupByLabels } from '../src/domain/admin/operations.ts'
import type { UsageGroupBy } from '../src/domain/admin/operations.ts'
import { failureRate, latency, usageColumns, usageKeyLabel } from '../src/presentation/admin/usageFormatting.ts'
import { percentile, summarizeUsage, usageRows } from '../src/mocks/fixtures/admin/aiUsage.ts'
import { adminHandlers } from '../src/mocks/handlers/admin.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'

test('운영 API는 빈 필터를 생략하고 서버의 확정 응답을 그대로 사용한다', async (t) => {
  const requests: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    requests.push(String(url))
    return new Response(JSON.stringify({ items: [], page: 0, size: 20, totalElements: 0 }), { headers: { 'Content-Type': 'application/json' } })
  })
  await adminApi.jobs('', '')
  await adminApi.audits({ from: '2026-01-01', to: '2026-01-07' }, '')
  await adminApi.missions({ status: '', grade: '', thinkingType: '' })
  assert.equal(new URL(requests[2], 'http://test').search, '')
  assert.equal(new URL(requests[0], 'http://test').searchParams.has('type'), false)
  assert.equal(new URL(requests[0], 'http://test').searchParams.has('status'), false)
  assert.equal(new URL(requests[1], 'http://test').searchParams.has('targetType'), false)
})

test('AI 사용량 조회는 묶음 기준을 쿼리로 보내고 기본은 호출 종류다 (#1051)', async (t) => {
  const urls: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    urls.push(String(url))
    return new Response(JSON.stringify({ period: { from: '2026-10-20', to: '2026-10-26' }, groupBy: 'DAY', items: [] }), { headers: { 'Content-Type': 'application/json' } })
  })
  await adminApi.usage({ from: '2026-10-20', to: '2026-10-26' }, '')
  await adminApi.usage({ from: '2026-10-20', to: '2026-10-26' }, 'JUDGMENT', 'DAY')
  const q = urls.map(u => new URL(u, 'http://test').searchParams)
  assert.equal(q[0].get('groupBy'), 'CALL_TYPE')
  assert.deepEqual([q[1].get('callType'), q[1].get('groupBy')], ['JUDGMENT', 'DAY'])
})

test('AI 사용량 표는 실패율·p50·p95 열을 두고 첫 열 제목과 묶음 값 표시가 묶음 기준을 따른다 (#1051)', () => {
  assert.deepEqual(usageColumns('CALL_TYPE'), ['호출 종류', '호출 / 실패', '실패율', '평균 지연', 'p50 지연', 'p95 지연', '입력 / 출력 토큰', '비용 (USD)'])
  assert.deepEqual(Object.keys(usageGroupByLabels), ['CALL_TYPE', 'MODEL', 'PROMPT_VERSION', 'ERROR_CODE', 'DAY'])
  assert.deepEqual((Object.keys(usageGroupByLabels) as UsageGroupBy[]).map(g => usageColumns(g)[0]), ['호출 종류', '모델', '프롬프트 버전', '오류 코드', '날짜 (KST)'])
  assert.equal(usageKeyLabel('CALL_TYPE', 'JUDGMENT'), '판정')
  assert.equal(usageKeyLabel('MODEL', 'gpt-6-luna'), 'gpt-6-luna')
  assert.equal(usageKeyLabel('DAY', '2026-10-20'), '2026-10-20 (화)')
  assert.equal(usageKeyLabel('ERROR_CODE', null), '오류 코드 없음 (성공 포함)')
  assert.equal(usageKeyLabel('PROMPT_VERSION', null), '기록 없음')
  assert.equal(failureRate({ calls: 3, failures: 1 }), '33.3%')
  assert.equal(failureRate({ calls: 20, failures: 0 }), '0.0%')
  assert.equal(latency(1234.6), '1,235ms')
  // 화면은 열 목록·묶음 선택·Grafana 안내를 실제로 쓴다
  const screen = readFileSync(new URL('../src/presentation/admin/AdminOperations.tsx', import.meta.url), 'utf8')
  const usage = screen.slice(screen.indexOf('function Usage('))
  assert.match(usage, /usageColumns\(shown\)/)
  assert.match(usage, /aria-label="묶음 기준"[\s\S]*usageGroupByLabels/)
  assert.match(usage, /실시간 지연·경보는 Grafana, 이 화면은 DB 기록 기간 집계입니다\./)
  assert.match(usage, /adminApi\.usage\(period, type, groupBy, signal\)/)
  assert.doesNotMatch(usage, /recharts|chart\.js|<canvas|<svg/i)
})

test('AI 사용량 목업은 core와 같은 규칙으로 묶음 기준을 바꿔 집계하고 허용 외 값은 400이다 (#1051)', async () => {
  assert.equal(percentile([100, 200, 300, 400, 1000], 0.5), 300)
  assert.ok(Math.abs(percentile([100, 200, 300, 400, 1000], 0.95) - 880) < 1e-9)
  const rows = usageRows({ from: '2026-10-20', to: '2026-10-26' })
  const byDay = summarizeUsage(rows, 'DAY', null)
  assert.deepEqual(byDay.map(u => u.key), ['2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-24', '2026-10-25', '2026-10-26'])
  assert.ok(byDay.every(u => u.callType === null && u.p50LatencyMs <= u.p95LatencyMs))
  const byType = summarizeUsage(rows, 'CALL_TYPE', null)
  assert.equal(byType.reduce((s, u) => s + u.calls, 0), rows.length)
  assert.ok(byType.every(u => u.callType === u.key))
  const errors = summarizeUsage(rows, 'ERROR_CODE', null)
  assert.equal(errors.at(-1)!.key, null)
  assert.ok(summarizeUsage(rows, 'MODEL', 'M2').every(u => u.key === 'm2-klue-essay@3.1-1112b' && u.costUsd === 0 && u.inputTokens === null))
  const handlers = [...adminHandlers, ...studentHandlers]
  setWorkspaceScenario('normal')
  const send = async (path: string, token = '', body?: unknown) => {
    const r = await getResponse(handlers, new Request('http://localhost/api/v1' + path, {
      method: body ? 'POST' : 'GET', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}),
    }), { baseUrl: 'http://localhost' })
    return { status: r!.status, data: await r!.json() }
  }
  const token = (await send('/auth/login', '', { email: 'ops@example.test', password: 'demo-only' })).data.accessToken
  const ok = await send('/admin/ai-usage?from=2026-10-20&to=2026-10-26&groupBy=DAY&callType=JUDGMENT', token)
  assert.equal(ok.status, 200)
  assert.equal(ok.data.groupBy, 'DAY')
  assert.equal(ok.data.items.length, 7)
  assert.equal((await send('/admin/ai-usage?from=2026-10-20&to=2026-10-26', token)).data.groupBy, 'CALL_TYPE')
  for (const bad of ['day', 'WEEK', 'call_type'])
    assert.equal((await send(`/admin/ai-usage?from=2026-10-20&to=2026-10-26&groupBy=${bad}`, token)).status, 400, bad)
  assert.equal((await send('/admin/ai-usage?from=2025-01-01&to=2026-01-02', token)).status, 400)
  assert.equal((await send('/admin/ai-usage?from=2025-01-01&to=2026-01-01', token)).status, 200)
})
