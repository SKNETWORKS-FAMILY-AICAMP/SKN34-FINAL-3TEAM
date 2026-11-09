import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { REAUTH_CHANNEL, subscribeReauthReturn } from '../src/data/reauthReturn.ts'

const tick = () => new Promise((resolve) => setTimeout(resolve, 20))

test('#425 재인증 콜백 탭의 알림은 같은 challengeId일 때 한 번만 원래 탭을 완료시킨다', async () => {
  let calls = 0
  const stop = subscribeReauthReturn('challenge-a', () => { calls += 1 })
  const sender = new BroadcastChannel(REAUTH_CHANNEL)
  try {
    sender.postMessage({ type: 'REAUTH_VERIFIED', challengeId: 'challenge-b' })
    sender.postMessage({ type: 'OTHER', challengeId: 'challenge-a' })
    sender.postMessage({ challengeId: 'challenge-a' })
    await tick()
    assert.equal(calls, 0)
    sender.postMessage({ type: 'REAUTH_VERIFIED', challengeId: 'challenge-a' })
    await tick()
    assert.equal(calls, 1)
    sender.postMessage({ type: 'REAUTH_VERIFIED', challengeId: 'challenge-a' })
    await tick()
    assert.equal(calls, 1)
  } finally {
    stop()
    sender.close()
  }
})

test('#425 구독 해제·빈 challengeId·BroadcastChannel 미지원이면 자동 완료하지 않는다', async () => {
  let calls = 0
  const stop = subscribeReauthReturn('challenge-c', () => { calls += 1 })
  stop()
  stop()
  const sender = new BroadcastChannel(REAUTH_CHANNEL)
  try {
    sender.postMessage({ type: 'REAUTH_VERIFIED', challengeId: 'challenge-c' })
    await tick()
    assert.equal(calls, 0)
  } finally {
    sender.close()
  }
  let opened = 0
  subscribeReauthReturn('', () => { calls += 1 }, () => { opened += 1; return null })()
  assert.equal(opened, 0)
  assert.doesNotThrow(() => subscribeReauthReturn('challenge-d', () => { calls += 1 }, () => null)())
})

test('#425 재인증 화면은 채널을 구독하고 수동 완료 확인과 opener=null을 유지한다', () => {
  for (const file of ['../src/presentation/parent/StudentDevices.tsx', '../src/presentation/service/AccountLifecycle.tsx']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8')
    assert.match(source, /useReauthReturn\(/, file)
    assert.match(source, /opener\s*=\s*null/, file)
    assert.match(source, /완료 확인/, file)
  }
  const devices = readFileSync(new URL('../src/presentation/parent/StudentDevices.tsx', import.meta.url), 'utf8')
  assert.equal(devices.match(/useReauthReturn\(/g)?.length, 2)
})
