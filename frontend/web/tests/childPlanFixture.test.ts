import test from 'node:test'
import assert from 'node:assert/strict'
import { fixtureStore } from '../src/mocks/fixtures/student.ts'
import { mockAccountChildren, mockIdentity } from '../src/mocks/fixtures/accounts.ts'
import { setMockChildPlan } from '../src/mocks/fixtures/childPlan.ts'
import { mockEntitlement } from '../src/mocks/fixtures/payments.ts'

test('테스트 플랜 설정은 가상 보호자 본인의 자녀 구독만 바꾸고, 신규 기본 이용권은 무료이며 자녀 정보에는 이용권이 없다', async () => {
  const child = { id: 'new-test-child', nickname: '가상 자녀', grade: 3, birthYear: 2017 }
  mockIdentity.email = 'test-new@example.test'
  mockAccountChildren.set(mockIdentity.email, [child])
  fixtureStore.replaceChildren([child])
  await fixtureStore.login(mockIdentity.email, 'demo-only')
  assert.equal(mockEntitlement(child.id).status, 'FREE')
  for (const invalid of [null, {}, { childId: child.id, plan: 'PAID' }, { childId: 'other-child', plan: 'PREMIUM' }])
    assert.equal(setMockChildPlan(invalid), false)
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'PREMIUM' }), true)
  assert.equal(mockEntitlement(child.id).product.code, 'PREMIUM')
  assert.equal('plan' in (await fixtureStore.children())[0], false)
  await fixtureStore.enterStudent(child)
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'FREE' }), false)
  await fixtureStore.login(mockIdentity.email, 'demo-only')
  mockIdentity.email = 'other@example.test'
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'FREE' }), false)
  mockIdentity.email = 'real@example.com'
  mockAccountChildren.set(mockIdentity.email, [child])
  assert.equal(setMockChildPlan({ childId: child.id, plan: 'FREE' }), false)
})
