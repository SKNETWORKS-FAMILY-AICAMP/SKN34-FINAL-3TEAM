import test from 'node:test'
import assert from 'node:assert/strict'
import { adminRetentionApi as api } from '../src/data/admin/retentionApi.ts'
import { ApiError, setAccessToken } from '../src/data/apiClient.ts'
import { themeDraftOf, themeDraftRequestErrors } from '../src/domain/admin/themeDrafts.ts'
import type { ThemeDraftRequest } from '../src/domain/admin/themeDrafts.ts'
import type { ThemeGrade } from '../src/domain/admin/retention.ts'

const draftId = '00000000-0000-4000-8000-000000000441'
const themeId = '00000000-0000-4000-8000-000000000395'
const input: ThemeDraftRequest = { grade: 'G3', weekStart: '2026-11-16' }

test('#441: 식별자·상태는 필수, 계약 밖 값(모르는 출처·잘못된 시각·모르는 초안 칸)은 비운 값으로 둔다', () => {
  // learning #438 상세 계약 확정(2026-11-12) 뒤: 상세 칸을 읽되 계약 밖 값은 해석하지 않는다
  const d = themeDraftOf({ draftId, status: 'GENERATING', draft: { invented: true }, source: 'UNKNOWN', createdAt: 0 })
  assert.equal(d.draftId, draftId)
  assert.equal(d.status, 'GENERATING')
  assert.equal(d.source, null)
  assert.equal(d.createdAt, null)
  assert.deepEqual(d.draft, { theme: null, missions: [], dialogues: [], warnings: [] })
  assert.deepEqual(d.scenes, [])
  for (const value of [null, [], {}, { draftId, status: 'SUCCESS' }, { draftId: '', status: 'READY' }]) assert.throws(() => themeDraftOf(value), /응답을 확인/)
})

test('#441: 요청은 월요일·학년과 기존 성취기준/입력 방식만 검사한다', () => {
  assert.deepEqual(themeDraftRequestErrors(input), [])
  assert.ok(themeDraftRequestErrors({ ...input, weekStart: '2026-11-17' }).length)
  assert.ok(themeDraftRequestErrors({ ...input, weekStart: '2026-02-30' }).length)
  const mission = { thinkingType: 'ANALYZE' as const, standardCodes: ['4과03-01'], inputType: 'NARRATIVE' as const }
  assert.deepEqual(themeDraftRequestErrors({ ...input, missions: [mission] }), [])
  assert.ok(themeDraftRequestErrors({ ...input, missions: [mission, mission] }).length)
  assert.ok(themeDraftRequestErrors({ ...input, missions: [{ ...mission, standardCodes: ['[4과03-01]'] }] }).length)
  assert.ok(themeDraftRequestErrors({ ...input, missions: [{ ...mission, inputType: 'ESSAY' }] }).length)
})

test('#441: 네 학년을 받고 초3·초4에서만 논술을 차단한다', () => {
  for (const grade of ['G3', 'G4', 'G5', 'G6'] as const) {
    assert.deepEqual(themeDraftRequestErrors({ ...input, grade }), [])
    const errors = themeDraftRequestErrors({ ...input, grade, missions: [{ thinkingType: 'EVALUATE', standardCodes: ['4국03-01'], inputType: 'ESSAY' }] })
    assert.equal(errors.includes('초3~4에는 논술을 지정할 수 없습니다.'), grade === 'G3' || grade === 'G4')
  }
  for (const grade of ['G3_4', 'G5_6', 'G2', 'G7', '3', 3, undefined]) {
    assert.ok(themeDraftRequestErrors({ ...input, grade: grade as ThemeGrade }).includes('학년을 선택해 주세요.'))
  }
})

test('#441: 초안 요청·기존 테마 저장·목록 필터는 grade만 전송한다', async t => {
  const calls: { url: URL; init: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url: new URL(url, 'http://localhost'), init })
    return Response.json(init.method === 'POST' && url.endsWith('/theme-drafts') ? { draftId, status: 'GENERATING' } : { items: [] })
  })
  for (const grade of ['G3', 'G4', 'G5', 'G6'] as const) {
    await api.requestThemeDraft({ ...input, grade })
    assert.deepEqual(JSON.parse(String(calls.at(-1)!.init.body)), { grade, weekStart: input.weekStart })
    await api.themes({ grade, status: 'DRAFT' })
    assert.equal(calls.at(-1)!.url.searchParams.get('grade'), grade)
    assert.equal(calls.at(-1)!.url.searchParams.has('gradeBand'), false)
    const body = { grade, weekStart: input.weekStart, title: '학년별 테마', intro: '도입', days: [] }
    await api.saveTheme(themeId, body)
    assert.deepEqual(JSON.parse(String(calls.at(-1)!.init.body)), body)
  }
})

// 아래 고정 HTTP 응답은 중계 경로·입출력 검사다. learning 생성 작업/상태 전이 목업을 구현하지 않는다.
test('#441: 공개 중계 경로·필터·본문·AbortSignal을 전달한다', async t => {
  setAccessToken('synthetic-admin', 'ADMIN'); t.after(() => setAccessToken(null))
  const calls: { url: string; init: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    const method = init.method ?? 'GET'
    calls.push({ url, init: { ...init, method } })
    return Response.json(url.endsWith('/adopt') ? { themeId } : method === 'GET' && url.includes('?') ? { items: [{ draftId, status: 'GENERATING' }] } : { draftId, status: 'GENERATING' })
  })
  const controller = new AbortController()
  const listed = await api.themeDrafts({ source: 'AUTO', status: 'GENERATING', page: '0', size: '20' }, controller.signal)
  assert.deepEqual(listed.items.map(d => [d.draftId, d.status]), [[draftId, 'GENERATING']])
  assert.equal(listed.totalElements, null) // 합계가 없으면 받은 개수로 다음 쪽 판단
  assert.equal(new URL(calls[0].url, 'http://localhost').searchParams.get('source'), 'AUTO')
  assert.equal(calls[0].init.signal, controller.signal)
  await api.themeDraft(draftId, controller.signal)
  await api.requestThemeDraft(input)
  assert.deepEqual(JSON.parse(String(calls[2].init.body)), input)
  for (const action of ['discard', 'regenerate'] as const) await api.themeDraftAction(draftId, action)
  assert.deepEqual(await api.adoptThemeDraft(draftId), { themeId })
  assert.deepEqual(calls.slice(1).map(call => [call.init.method, call.url]), [
    ['GET', `/api/v1/admin/theme-drafts/${draftId}`], ['POST', '/api/v1/admin/theme-drafts'],
    ['POST', `/api/v1/admin/theme-drafts/${draftId}/discard`], ['POST', `/api/v1/admin/theme-drafts/${draftId}/regenerate`], ['POST', `/api/v1/admin/theme-drafts/${draftId}/adopt`],
  ])
  for (const call of calls.slice(3)) assert.equal(call.init.body, '{}')
})

test('#441: 503·미구현 응답을 성공/빈 목록으로 바꾸거나 쓰기를 자동 재요청하지 않는다', async t => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json({ status: 503, code: 'LEARNING_UNAVAILABLE', title: '요청 결과를 확인하지 못했습니다.' }, { status: 503 }) })
  await assert.rejects(api.requestThemeDraft(input), (e: unknown) => e instanceof ApiError && e.problem.code === 'LEARNING_UNAVAILABLE')
  assert.equal(calls, 1)
  await assert.rejects(api.themeDrafts({}), ApiError)
})
