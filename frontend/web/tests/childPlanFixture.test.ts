import test from 'node:test'
import assert from 'node:assert/strict'
import { fixtureStore } from '../src/mocks/fixtures/student.ts'
import { mockAccountChildren, mockIdentity } from '../src/mocks/fixtures/accounts.ts'
import { setMockChildPlan } from '../src/mocks/fixtures/childPlan.ts'

test('테스트 플랜 설정은 가상 보호자 본인의 자녀만 허용, 신규 기본 요금제는 FREE', async () => {
  const child = { id: 'new-test-child', nickname: '가상 자녀', grade: 3, birthYear: 2017, plan: 'FREE' as const }
  mockIdentity.email = 'test-new@example.test'
  mockAccountChildren.set(mockIdentity.email, [child])
  fixtureStore.replaceChildren([child])
  await fixtureStore.login(mockIdentity.email, 'demo-only')
  assert.equal((await fixtureStore.children())[0].plan, 'FREE')
  for (const invalid of [null, {}, { childId: child.id, plan: 'PAID' }, { childId: 'other-child', plan: 'PREMIUM' }])
    assert.equal(setMockChildPlan(invalid), false)
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'PREMIUM' }), true)
  assert.equal((await fixtureStore.children())[0].plan, 'PREMIUM')
  await fixtureStore.enterStudent({ ...child, plan: 'PREMIUM' })
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'FREE' }), false)
  await fixtureStore.login(mockIdentity.email, 'demo-only')
  mockIdentity.email = 'other@example.test'
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'FREE' }), false)
  mockIdentity.email = 'real@example.com'
  mockAccountChildren.set(mockIdentity.email, [child])
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'FREE' }), false)
})
