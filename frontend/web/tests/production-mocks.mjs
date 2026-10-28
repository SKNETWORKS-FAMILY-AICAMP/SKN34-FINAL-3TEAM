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
  'fixtureStore',
  'msw-access-',
  'msw-consent-',
  'msw-conversation-',
  'demo-seoyun',
  'Mocking enabled',
  'MOCK_NOT_IMPLEMENTED',
  'mockAccountChildren',
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
console.log('운영 JS에 MSW·핸들러·가상 학생 fixture 없음 / 개발 worker 빌드 복사본 제외 확인')
