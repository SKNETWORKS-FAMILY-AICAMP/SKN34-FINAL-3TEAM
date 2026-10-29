// #134 웹 실서버 모드: core OpenAPI 응답 모양(ChildListItemPage·ReportList·ReportDetail)으로 어댑터를 검증한다.
import test from 'node:test'
import assert from 'node:assert/strict'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { parentApi } from '../src/data/parent/api.ts'
import { studentDeviceApi } from '../src/data/studentDevice/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
import { previousWeek } from '../src/domain/classroom.ts'
import type { Child } from '../src/domain/classroom.ts'

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
// 실서버 /children 항목에는 plan이 없다(api-spec 5.3)
const child: Child = { id: 'child-1', nickname: '가상 학생', grade: 3, birthYear: 2017 }
const summary = {
  reportId: 'r-1',
  childId: child.id,
  period: previousWeek,
  status: 'COMPLETED',
  state: 'OK',
  revision: 1,
  generatedAt: '2026-10-27T07:00:00+09:00',
}
const detail = (extra: Record<string, unknown>) => ({
  ...summary,
  revisions: [{ revision: 1, generatedAt: summary.generatedAt }],
  inclusionRule: '완료한 시도만 포함',
  metrics: [],
  thinkingTypes: [],
  changes: [],
  reflections: [],
  quotes: [],
  eveningQuestion: null,
  narrative: null,
  verification: { numbersMatched: true, quotesMatched: true },
  versions: {},
  ...extra,
})
function serve(t: test.TestContext, report: unknown) {
  const paths: string[] = []
  setAccessToken('memory-test-token')
  t.mock.method(globalThis, 'fetch', async (path: string) => {
    paths.push(String(path))
    if (path.endsWith(`/children/${child.id}/reports`)) return json({ items: [summary] })
    if (path.includes('/reports/r-1')) return json(report)
    if (path.includes(`/children/${child.id}/attempts`))
      return json({ childId: child.id, period: previousWeek, state: 'NO_RECORD', items: [], page: 0, size: 100, totalElements: 0 })
    return json({ code: 'NOT_FOUND', status: 404 }, 404)
  })
  return paths
}

test('자녀 목록의 plan 미제공은 미확인으로 두고 무료로 단정하지 않음', async (t) => {
  setAccessToken('memory-test-token')
  t.mock.method(globalThis, 'fetch', async () =>
    json({
      items: [{ id: child.id, nickname: child.nickname, grade: 3, birthYear: 2017, guardianConsentRequired: false,
        hasRecords: true, recordState: 'AVAILABLE', pinSet: true, pinLocked: false }],
      page: 0, size: 1, totalElements: 1,
    }),
  )
  const [row] = await createApiGateway().children()
  assert.equal(row.id, child.id)
  assert.equal(row.plan, undefined)
  setAccessToken(null)
})

test('plan이 없어도 서버가 준 서술·저녁 질문을 표시하고 숫자·인용 대조를 검사', async (t) => {
  const paths = serve(t, detail({
    eveningQuestion: '오늘 어떤 생각을 더 적고 싶었나요?',
    narrative: { text: '서버가 대조를 마친 요약', source: 'LLM', modelExplanation: null },
  }))
  const report = await createApiGateway().report(child, previousWeek)
  assert.equal(report.eveningQuestion, '오늘 어떤 생각을 더 적고 싶었나요?')
  assert.equal(report.narrative, '서버가 대조를 마친 요약')
  assert.ok(paths[0].endsWith(`/children/${child.id}/reports`)) // 목록은 {items}만(ReportList)
  setAccessToken(null)
})

test('plan이 없어도 서술이 있는데 대조 실패면 성공으로 표시하지 않음', async (t) => {
  serve(t, detail({
    narrative: { text: '대조 실패 서술', source: 'LLM', modelExplanation: null },
    verification: { numbersMatched: false, quotesMatched: true },
  }))
  await assert.rejects(createApiGateway().report(child, previousWeek), /대조/)
  setAccessToken(null)
})

test('무료 응답(narrative·eveningQuestion null)은 수치만', async (t) => {
  serve(t, detail({}))
  const report = await createApiGateway().report(child, previousWeek)
  assert.equal(report.narrative, null)
  assert.equal(report.eveningQuestion, undefined)
  setAccessToken(null)
})

test('리포트 목록은 {items} 그대로, 자녀 수정은 바꾼 필드만 헤더 없이', async (t) => {
  const sent: { url: string; init: RequestInit }[] = []
  setAccessToken('memory-test-token')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    sent.push({ url: String(url), init })
    return String(url).includes('/reports') ? json({ items: [summary] }) : json({ id: child.id, nickname: child.nickname, grade: 4, birthYear: 2017 })
  })
  assert.deepEqual(await parentApi.reports(child.id, 'COMPLETED'), { items: [summary] })
  assert.match(sent[0].url, /\/children\/child-1\/reports\?status=COMPLETED$/)
  await parentApi.updateChild(child.id, { grade: 4 })
  assert.equal(sent[1].init.method, 'PATCH')
  assert.deepEqual(JSON.parse(String(sent[1].init.body)), { grade: 4 })
  assert.equal(new Headers(sent[1].init.headers).get('X-Reauth-Token'), null)
  setAccessToken(null)
})

test('학생 PIN 로그인 응답에 plan이 없으면 미확인', async (t) => {
  t.mock.method(globalThis, 'fetch', async () =>
    json({ role: 'STUDENT', accessToken: 'student-token', child: { childId: child.id, nickname: child.nickname, grade: 3 } }),
  )
  const session = await studentDeviceApi.login(child.id, '1234')
  assert.equal(session.role === 'STUDENT' && session.child.plan, undefined)
  setAccessToken(null)
})
