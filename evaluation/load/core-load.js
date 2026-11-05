// AWS 데모 core·NAT 병목 부하 시험 (#361). 사용법·비밀 파일 형식·중단 기준은 README.md.
// 한 번 실행 = VU 단계 하나(올리기 30초 → 유지 HOLD → 내리기). 단계마다 setup()에서 토큰을 새로 받는다.
import http from 'k6/http'
import { check, sleep } from 'k6'
import exec from 'k6/execution'
import { Counter, Rate, Trend } from 'k6/metrics'

const ORIGIN = (__ENV.BASE_URL || 'https://d3jf0rnm6vhd9v.cloudfront.net').replace(/\/$/, '')
// 쿠키 인증 경로(refresh·학생 로그인)는 CSRF 방어로 Origin이 웹 주소와 같아야 한다(PublicAuthFilter).
const BASE = `${ORIGIN}/api/v1`
const SECRETS_PATH = __ENV.LOAD_SECRETS
if (!SECRETS_PATH) throw new Error('LOAD_SECRETS(저장소 밖 비밀 파일 절대 경로)가 필요합니다.')
const SECRETS = JSON.parse(open(SECRETS_PATH))
if (!Array.isArray(SECRETS.accounts) || SECRETS.accounts.length === 0) throw new Error('비밀 파일에 accounts가 없습니다.')

const VUS = Number(__ENV.VUS || 10)
const HOLD = __ENV.HOLD || '5m'
const RAMP = __ENV.RAMP || '30s'
const MISSION_INPUT_TYPES = (__ENV.MISSION_INPUT_TYPES || 'NARRATIVE,ESSAY,SOLUTION_STEPS').split(',').map((t) => t.trim())
const ANALYZE_RATIO = Number(__ENV.ANALYZE_RATIO ?? 0.1)
const NOTIFY_HOLD_S = Number(__ENV.NOTIFY_HOLD_S || 120)
const RESULT_DIR = __ENV.RESULT_DIR || ''
const P95_API_MS = Number(__ENV.P95_API_MS || 1000)
const P95_JUDGMENT_MS = Number(__ENV.P95_JUDGMENT_MS || 30000)
const P95_ANALYSIS_MS = Number(__ENV.P95_ANALYSIS_MS || 60000)

// 조회 55%, 학습 20%, 알림 연결 15%, 분석 대화 10%(유료 보호자). ANALYZE_RATIO=0이면 분석을 끄고 나머지를 그대로 둔다.
const split = (ratio) => Math.max(1, Math.round(VUS * ratio))
const stages = (target) => [
  { duration: RAMP, target },
  { duration: HOLD, target },
  { duration: '10s', target: 0 },
]
const scenarios = {
  browse: { executor: 'ramping-vus', exec: 'browse', startVUs: 0, stages: stages(split(0.55)), gracefulRampDown: '10s' },
  learn: { executor: 'ramping-vus', exec: 'learn', startVUs: 0, stages: stages(split(0.2)), gracefulRampDown: '90s' },
  notify: { executor: 'ramping-vus', exec: 'notify', startVUs: 0, stages: stages(split(0.15)), gracefulRampDown: '0s' },
}
if (ANALYZE_RATIO > 0)
  scenarios.analyze = { executor: 'ramping-vus', exec: 'analyze', startVUs: 0, stages: stages(split(ANALYZE_RATIO)), gracefulRampDown: '130s' }

const abort = (expr) => ({ threshold: expr, abortOnFail: true, delayAbortEval: '1m' })
// 경로별 p95를 요약에 남기기 위한 관찰용 임계값(항상 통과).
const NAMES = ['me', 'reports', 'report_detail', 'notifications', 'conversations', 'missions', 'mission_detail', 'student_home',
  'student_attempts', 'attempt_start', 'answer_submit', 'feedback_sse', 'attempt_finish', 'attempt_reflection',
  'conversation_create', 'analysis_sse']
const observe = Object.fromEntries(NAMES.map((name) => [`http_req_duration{name:${name}}`, ['max>=0']]))
export const options = {
  scenarios,
  setupTimeout: '60s',
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    ...observe,
    // 중단 기준: API 오류율 1% 초과, API p95 목표 초과. Pod 재시작·RDS CPU 80%는 README 절차로 사람이 본다.
    'http_req_failed{kind:api}': [abort('rate<0.01')],
    'http_req_duration{kind:api}': [abort(`p(95)<${P95_API_MS}`)],
    judgment_duration: [`p(95)<${P95_JUDGMENT_MS}`],
    analysis_duration: [`p(95)<${P95_ANALYSIS_MS}`],
    analysis_ok: ['rate>0.99'],
    learn_ok: ['rate>0.99'],
    notify_ok: ['rate>0.99'],
  },
}

const judgmentDuration = new Trend('judgment_duration', true)
const analysisDuration = new Trend('analysis_duration', true)
const learnOk = new Rate('learn_ok')
const notifyOk = new Rate('notify_ok')
const analysisOk = new Rate('analysis_ok')
const learnConflict = new Counter('learn_conflict')
const analysisLimited = new Counter('analysis_limited')

// 경합·한도처럼 예상한 상태는 오류율에서 빼고 별도 카운터로 센다.
const allow = (...codes) => http.expectedStatuses({ min: 200, max: 299 }, ...codes)
const headers = (token, extra = {}) => ({
  Authorization: `Bearer ${token}`,
  'X-Requested-With': 'XMLHttpRequest',
  'Content-Type': 'application/json',
  ...extra,
})
const params = (token, name, kind = 'api', extra = {}) => ({ headers: headers(token), tags: { name, kind }, ...extra })
const json = (res) => {
  try { return res.json() } catch { return null }
}
const uuid = () =>
  'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
// Spring SseEmitter는 'event:result'처럼 콜론 뒤 공백 없이 쓴다. 공백·CRLF 유무와 관계없이 이벤트 이름 줄을 찾는다.
const sseEvent = (body, name) => body.split('\n').some((line) => line.replace(/^event:\s*/, '').trim() === name && line.startsWith('event:'))
const think = () => sleep(1 + Math.random() * 2)
const today = () => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10)
const daysAgo = (n) => new Date(Date.now() + 9 * 3600 * 1000 - n * 86400 * 1000).toISOString().slice(0, 10)

// 비밀 값은 출력하지 않는다. 실패 시 상태 코드와 오류 code만 남긴다.
function fail(step, res) {
  const code = json(res)?.code ?? ''
  throw new Error(`${step} 실패: HTTP ${res.status} ${code}`)
}

// 순서 주의: 보호자 refresh는 쓰는 순간 회전한다. 실패할 수 있는 단계(학생 로그인·미션 조회)를 먼저 끝내고,
// 갱신 뒤에는 예외를 던지지 않아야 handleSummary가 새 refresh 토큰을 비밀 파일에 저장할 수 있다.
export function setup() {
  const students = SECRETS.accounts.map((account, i) =>
    account.children.map((child, j) => {
      const login = http.post(`${BASE}/auth/student/login`, JSON.stringify({ childId: child.childId, pin: child.pin }), {
        headers: { Cookie: `student_device=${account.deviceCookie}`, 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', Origin: ORIGIN },
        tags: { name: 'auth_student_login', kind: 'setup' },
      })
      if (login.status !== 200) fail(`학생 로그인(계정 ${i}, 자녀 ${j})`, login)
      return { childId: child.childId, token: json(login).accessToken }
    }))

  // 미션은 학년 범위에 따라 자녀마다 다르다. 자녀별로 받아 (자녀, 미션) 칸 목록을 만든다.
  const seen = new Set()
  for (const child of students.flat()) {
    const listed = http.get(`${BASE}/missions`, params(child.token, 'missions', 'setup'))
    if (listed.status !== 200) fail('미션 목록', listed)
    const all = json(listed).items ?? []
    child.missions = all.filter((m) => MISSION_INPUT_TYPES.includes(m.inputType)).map((m) => ({ id: m.missionId ?? m.id, inputType: m.inputType }))
    // 학년 범위에 맞는 미션이 없는 자녀는 학습에서 빼고 조회에만 쓴다.
    child.missions.forEach((m) => seen.add(m.id))
  }
  const missions = [...seen]
  if (missions.length === 0) throw new Error(`어느 자녀에게도 ${MISSION_INPUT_TYPES.join('·')} 미션이 없습니다.`)

  // 여기부터 예외 금지. 갱신에 실패한 계정은 기존 토큰을 그대로 두고 시험을 멈춘다.
  let abortReason = null
  const accounts = SECRETS.accounts.map((account, i) => {
    const refreshed = http.post(`${BASE}/auth/refresh`, null, {
      headers: { Cookie: `sagomungchi_refresh=${account.refreshToken}`, 'X-Requested-With': 'XMLHttpRequest', Origin: ORIGIN },
      tags: { name: 'auth_refresh', kind: 'setup' },
    })
    const rotated = refreshed.status === 200 ? refreshed.cookies.sagomungchi_refresh?.[0]?.value : undefined
    const parentToken = json(refreshed)?.accessToken
    if (!rotated || !parentToken) abortReason ??= `보호자 토큰 갱신(계정 ${i}) 실패: HTTP ${refreshed.status} ${json(refreshed)?.code ?? ''}`
    return { parentToken, rotated: rotated ?? account.refreshToken, children: students[i] }
  })
  if (abortReason) return { abortReason, accounts, missions }

  // 리포트 상세 보기 대상: 자녀별 첫 리포트. 없으면 상세 보기를 건너뛴다.
  for (const account of accounts)
    for (const child of account.children) {
      const res = http.get(`${BASE}/children/${child.childId}/reports`, params(account.parentToken, 'reports', 'setup'))
      const items = res.status === 200 ? json(res)?.items ?? [] : []
      child.reportId = items.map((r) => r.reportId).find(Boolean) ?? null
    }
  return { accounts, missions }
}

// setup이 보호자 토큰 갱신에 실패했으면 부하를 주지 않고 바로 멈춘다(새 토큰 저장은 handleSummary가 한다).
function guard(data) {
  if (data.abortReason) exec.test.abort(data.abortReason)
}

function pick(data) {
  const vu = exec.vu.idInTest
  const account = data.accounts[vu % data.accounts.length]
  const child = account.children[vu % account.children.length]
  return { account, child }
}

// 조회: 보호자 화면과 학생 화면을 번갈아 본다.
export function browse(data) {
  guard(data)
  const { account, child } = pick(data)
  const p = account.parentToken
  const s = child.token
  const mission = child.missions.length ? child.missions[(exec.vu.iterationInScenario + exec.vu.idInTest) % child.missions.length].id : null
  const calls = [
    [`${BASE}/me`, p, 'me'],
    [`${BASE}/children/${child.childId}/reports`, p, 'reports'],
    [`${BASE}/notifications?unreadOnly=false&page=0&size=20`, p, 'notifications'],
    // 대화 목록은 학생 공개 설정을 따른다(비공개면 403 STUDENT_RECORDS_PRIVATE). 분석을 쓰는 첫 자녀로만 본다.
    [`${BASE}/conversations?childId=${account.children[0].childId}`, p, 'conversations'],
    [`${BASE}/missions`, s, 'missions'],
    [`${BASE}/students/me/home`, s, 'student_home'],
    [`${BASE}/students/me/attempts`, s, 'student_attempts'],
  ]
  // 유료 리포트 상세는 볼 때마다 이용 기록(REPORT_VIEW)을 쓴다.
  if (mission) calls.splice(calls.length - 2, 0, [`${BASE}/missions/${mission}`, s, 'mission_detail'])
  if (child.reportId) calls.splice(2, 0, [`${BASE}/reports/${child.reportId}`, p, 'report_detail'])
  for (const [url, token, name] of calls) {
    const res = http.get(url, params(token, name))
    if (!check(res, { [`${name} 200`]: (r) => r.status === 200 }))
      debug(`browse ${name} child=${data.accounts.flatMap((x) => x.children).indexOf(child)} HTTP ${res.status} ${json(res)?.code ?? ''}`)
    think()
  }
}

// 학습 VU마다 첫 반복에서 (자녀, 미션) 칸 하나를 맡는다. 시도는 자녀×미션마다 하나만 진행되므로
// 판정 동시성 상한은 자녀 수 × 미션 수다. 첫 칸은 VU 번호로 정하지만 학습 VU 번호가 이어진다는 보장이 없어
// 겹칠 수 있다. 그래서 경합을 만나면 다음 칸으로 옮겨, 학습 VU가 칸 수 이하이면 곧 서로 다른 칸에 자리 잡는다.
let learnSlot = null
const ANSWERS = {
  NARRATIVE: { text: '나는 친구와 나누어 쓰는 것이 좋다고 생각해. 왜냐하면 같이 쓰면 모두 즐겁기 때문이야.' },
  ESSAY: { essay: { claim: '쉬는 시간은 더 길어야 한다고 생각해.', reasons: ['몸을 움직이면 집중이 잘 돼.', '친구와 이야기하며 생각을 나눌 수 있어.'], rebuttal: '수업 시간이 줄어든다는 걱정도 있지만 집중이 좋아지면 괜찮아.' } },
  SOLUTION_STEPS: { finalAnswer: '12', steps: ['문제에서 알려 준 수를 정리한다.', '필요한 식을 세워 계산한다.'] },
}
// 학습: 시도 시작 → 첫 답변 제출 → 판정 SSE 완료까지 → 마무리 → 돌아보기(완료).
// 같은 자녀·미션을 여러 VU가 동시에 잡으면 진행 중 시도를 같이 받으므로, 그 경합은 learn_conflict로 센다.
export function learn(data) {
  guard(data)
  const children = data.accounts.flatMap((a) => a.children)
  // 칸 목록을 자녀를 번갈아 가며 늘어놓아, VU가 적을 때도 자녀에게 고르게 나뉘게 한다.
  const slots = []
  for (let i = 0; slots.length < children.reduce((n, c) => n + c.missions.length, 0); i++)
    for (const c of children) if (i < c.missions.length) slots.push({ child: c, mission: c.missions[i] })
  learnSlot ??= exec.vu.idInTest
  const { child, mission } = slots[learnSlot % slots.length]
  const s = child.token

  const started = http.post(`${BASE}/missions/${mission.id}/attempts`, '{}', params(s, 'attempt_start'))
  if (!check(started, { 'attempt_start 200/201': (r) => r.status === 200 || r.status === 201 })) {
    debug(`attempt_start child=${children.indexOf(child)} HTTP ${started.status} ${json(started)?.code ?? ''}`)
    learnOk.add(false)
    return think()
  }
  const attempt = json(started)
  const answers = attempt.answers ?? []
  if (answers.length > 0) {
    // 다른 VU(또는 이전 실행)가 이미 답한 시도: 판정이 안 끝났으면 끝내고 마무리·완료해 다음 반복이 새 시도를 받게 한다.
    learnConflict.add(1)
    learnSlot++
    const last = answers[answers.length - 1]
    debug(`conflict answers=${answers.length} status=${attempt.status} lastFeedback=${last.feedback?.status} next=${(attempt.nextActions ?? []).join(',')}`)
    if (last.feedback?.status !== 'DONE')
      http.post(`${BASE}/answers/${last.answerId}/feedback`, null,
        { ...params(s, 'feedback_sse_resume', 'sse'), headers: headers(s, { Accept: 'text/event-stream' }), timeout: '100s' })
    close(s, attempt.attemptId)
    return think()
  }
  think()

  const submitted = http.post(`${BASE}/attempts/${attempt.attemptId}/answers`,
    JSON.stringify({ inputType: mission.inputType, ...ANSWERS[mission.inputType], dictatedByGuardian: false }),
    { ...params(s, 'answer_submit'), headers: headers(s, { 'Idempotency-Key': uuid() }), responseCallback: allow(409, 422) })
  if (submitted.status === 409 || submitted.status === 422) {
    learnConflict.add(1)
    learnSlot++
    return think()
  }
  if (!check(submitted, { 'answer_submit 201': (r) => r.status === 201 })) {
    debug(`answer_submit child=${children.indexOf(child)} ${mission.inputType} HTTP ${submitted.status} ${json(submitted)?.code ?? ''}`)
    learnOk.add(false)
    return think()
  }
  const answerId = json(submitted).answerId

  // 판정 SSE: k6 기본 http는 스트림이 끝날 때까지 기다린 뒤 한 번에 받는다(core 쪽 최대 80초 + done).
  const feedback = http.post(`${BASE}/answers/${answerId}/feedback`, null,
    { ...params(s, 'feedback_sse', 'sse'), headers: headers(s, { Accept: 'text/event-stream' }), timeout: '100s' })
  const body = feedback.body ?? ''
  const done = feedback.status === 200 && sseEvent(body, 'result') && /"status": ?"DONE"/.test(body)
  judgmentDuration.add(feedback.timings.duration, { done: String(done) })
  if (feedback.status === 200 && !done && !sseEvent(body, 'error')) {
    learnConflict.add(1) // 다른 요청이 판정 중(RUNNING만 받고 종료)
    return think()
  }
  learnOk.add(done)
  if (!done) return
  think()
  close(s, attempt.attemptId)
}

function close(token, attemptId) {
  // 이미 마무리한 시도·판정 전 시도는 409. 어느 쪽이든 돌아보기까지 시도해 완료 상태로 만든다.
  const finished = http.post(`${BASE}/attempts/${attemptId}/finish`, '{}', { ...params(token, 'attempt_finish'), responseCallback: allow(409) })
  const reflected = http.post(`${BASE}/attempts/${attemptId}/reflection`, JSON.stringify({ difficulty: 'NORMAL' }),
    { ...params(token, 'attempt_reflection'), responseCallback: allow(409) })
  debug(`close finish=${finished.status} ${json(finished)?.code ?? ''} reflection=${reflected.status} ${json(reflected)?.code ?? ''}`)
}
// DEBUG=1일 때만 상태 코드와 오류 code를 출력한다(토큰·본문 원문은 출력하지 않는다).
function debug(message) {
  if (__ENV.DEBUG) console.log(message)
}

// 알림 SSE: 보호자가 화면을 켜 둔 상태. 서버는 5분 뒤 닫으므로 NOTIFY_HOLD_S만큼 붙잡았다가 다시 연결한다.
// k6 시간 초과(오류 코드 1050)는 연결이 그만큼 유지됐다는 뜻이라 성공으로 본다.
export function notify(data) {
  guard(data)
  const { account } = pick(data)
  const res = http.get(`${BASE}/notifications/stream`, {
    headers: headers(account.parentToken, { Accept: 'text/event-stream' }),
    tags: { name: 'notifications_stream', kind: 'hold' },
    timeout: `${NOTIFY_HOLD_S}s`,
  })
  notifyOk.add(res.status === 200 || res.error_code === 1050)
  sleep(1)
}

// 분석 대화 SSE(유료 보호자): VU마다 대화를 하나 만들고, 질문 → 결과까지 받기 → 30~60초 생각을 반복한다.
// 한도·권한 응답(409·429)은 analysis_limited로 센다. clarification은 서버가 정상 종료한 응답이라 성공으로 본다.
const QUESTIONS = ['이번 주에 되묻기를 받고 생각을 더 쓴 적이 몇 번이야?', '지난주보다 답을 끝까지 쓴 날이 늘었어?', '어떤 생각 유형 미션을 가장 많이 했어?']
let conversationId = null
export function analyze(data) {
  guard(data)
  const { account } = pick(data)
  const child = account.children[0] // 분석은 활성 구독이 있는 첫 번째 자녀로만 보낸다
  const p = account.parentToken
  if (!conversationId) {
    const created = http.post(`${BASE}/conversations`, JSON.stringify({ childId: child.childId, from: daysAgo(6), to: today() }),
      { ...params(p, 'conversation_create'), responseCallback: allow(409, 429) })
    if (created.status === 409 || created.status === 429) { analysisLimited.add(1); return sleep(30) }
    conversationId = json(created)?.conversationId
    if (!conversationId) { analysisOk.add(false); return sleep(30) }
  }
  const res = http.post(`${BASE}/conversations/${conversationId}/messages`,
    JSON.stringify({ question: QUESTIONS[exec.vu.iterationInScenario % QUESTIONS.length] }),
    { ...params(p, 'analysis_sse', 'sse'), headers: headers(p, { Accept: 'text/event-stream' }), timeout: '130s',
      responseCallback: allow(409, 429) })
  if (res.status === 409 || res.status === 429) { analysisLimited.add(1); return sleep(30) }
  const body = res.body ?? ''
  analysisOk.add(res.status === 200 && (sseEvent(body, 'result') || sseEvent(body, 'clarification')))
  analysisDuration.add(res.timings.duration)
  sleep(30 + Math.random() * 30)
}

// 회전된 보호자 refresh 토큰을 비밀 파일에 되돌려 써서 다음 단계가 이어 쓰게 한다. 결과에는 지표만 남긴다.
export function handleSummary(data) {
  const out = {}
  const setup = data.setup_data
  if (setup?.accounts) {
    const next = { ...SECRETS, accounts: SECRETS.accounts.map((a, i) => ({ ...a, refreshToken: setup.accounts[i].rotated })) }
    out[SECRETS_PATH] = JSON.stringify(next, null, 2)
  }
  const stamp = new Date(Date.now() + 9 * 3600 * 1000).toISOString().replace(/[:.]/g, '-').slice(0, 19)
  if (RESULT_DIR) out[`${RESULT_DIR.replace(/[\\/]$/, '')}/${stamp}-vus${VUS}.json`] = JSON.stringify({ vus: VUS, hold: HOLD, metrics: data.metrics }, null, 2)
  out.stdout = summary(data)
  return out
}

function summary(data) {
  const lines = [`
== core 부하 시험 VUS=${VUS} HOLD=${HOLD} 학습 미션 ${data.setup_data?.missions?.length ?? '?'}개, (자녀×미션) 칸 ${(data.setup_data?.accounts ?? []).flatMap((a) => a.children).reduce((n, c) => n + (c.missions?.length ?? 0), 0)}개 ==`]
  for (const [name, metric] of Object.entries(data.metrics).sort(([a], [b]) => a.localeCompare(b))) {
    const v = metric.values
    const bad = metric.thresholds && Object.values(metric.thresholds).some((t) => !t.ok) ? '  ✗ 임계값 초과' : ''
    if (metric.type === 'trend' && v['p(95)'] !== undefined)
      lines.push(`${name.padEnd(48)} p95=${v['p(95)'].toFixed(0)}ms p99=${v['p(99)'].toFixed(0)}ms max=${v.max.toFixed(0)}ms${bad}`)
    else if (metric.type === 'rate') lines.push(`${name.padEnd(48)} ${(v.rate * 100).toFixed(2)}% (${v.passes}/${v.passes + v.fails})${bad}`)
    else if (metric.type === 'counter') lines.push(`${name.padEnd(48)} ${v.count}${bad}`)
  }
  return lines.join('\n') + '\n'
}
