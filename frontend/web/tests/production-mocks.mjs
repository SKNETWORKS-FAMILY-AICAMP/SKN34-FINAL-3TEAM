import { readdir, readFile, access } from 'node:fs/promises'
import assert from 'node:assert/strict'
const root = new URL('../dist/', import.meta.url)
await assert.rejects(
  access(new URL('mockServiceWorker.js', root)),
  '운영 산출물에 개발 worker가 없어야 합니다.',
)
const files = await readdir(new URL('assets/', root))
const js = await Promise.all(
  files.filter((f) => f.endsWith('.js')).map((f) => readFile(new URL('assets/' + f, root), 'utf8')),
)
assert.ok(js.length)
for (const marker of [
  'setupWorker',
  'demo-refund-1',
  'demo-payment-1',
  'demo-admin-inquiry',
  'demo-pin-student',
  '가상 학생으로 PIN 로그인 준비',
  '/auth/student/demo-device',
  'fixtureStore',
  'msw-access-',
  'msw-consent-',
  'msw-conversation-',
  'demo-seoyun',
  'Mocking enabled',
  'MOCK_NOT_IMPLEMENTED',
  'mockAccountChildren',
  '가상 리포트 알림 예시',
  '요구사항 구현 점검',
  'mock-reviewer',
  'content-1',
  'mock-report-files',
  'sagomungchi:test-child-plan',
  'setMockChildPlan',
  // #59 학생 기기: 기기 쿠키를 대신하는 개발용 상태·상태 선택기
  'sagomungchi:msw-device',
  'sagomungchi:device-scenario',
  'setDeviceScenario',
  'startDeviceStudentSession',
  'startSharedDemo',
  'sagomungchi:qr-demo-owner',
  '/__demo/device',
  'X-Sagomungchi-Demo',
  'sagomungchi_demo_device',
  '두 기기 QR 시연',
  '기기 상태 시연',
  // 학생 꾸미기 설정 목업 저장소
  'sagomungchi:msw-look',
])
  assert.equal(
    js.some((s) => s.includes(marker)),
    false,
    `운영 JS에 목 표시 포함: ${marker}`,
  )
// #170: 개발 전용 PIN이 축약된 운영 JS 문자열로 남아 있지 않아야 합니다.
assert.equal(js.some((s) => /(['"`])5090\1/.test(s)), false, '운영 JS에 시연 PIN 포함')
// #97: 실제 모드에는 이메일 로그인·가입·비밀번호 재확인 호출이 없다 (학부모 Google 인증, 학생 기기·PIN)
for (const [pattern, name] of [
  [/["'`]\/auth\/login["'`]/, '/auth/login'],
  [/["'`]\/auth\/signup["'`]/, '/auth/signup'],
  [/\/me\/reauth["'`][^;]{0,80}password/, '/me/reauth {password}'],
])
  assert.equal(js.some((s) => pattern.test(s)), false, `운영 JS에 제거한 호출 포함: ${name}`)
console.log('운영 JS에 MSW·핸들러·가상 학생 fixture 없음 / 개발 worker 빌드 복사본 제외 확인')
