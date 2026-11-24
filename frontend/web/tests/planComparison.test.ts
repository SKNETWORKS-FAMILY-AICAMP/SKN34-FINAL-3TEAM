import test from 'node:test'
import assert from 'node:assert/strict'
import { MEMORY_BOOK_FREE, PLAN_NONE, comparisonProducts, planComparison } from '../src/domain/planComparison.ts'
import { freeProduct, premiumProduct } from '../src/mocks/fixtures/payments.ts'
import type { PaymentProduct } from '../src/domain/payment.ts'

const cells = (table: ReturnType<typeof planComparison>) =>
  Object.fromEntries(table.groups.flatMap(group => group.rows).map(row => [row.label, [row.free, row.premium]]))

test('#998 비교표: 상품 값(가격·일요일·추가 미션·물어보기·그림책)과 고정 문구를 칸에 넣는다', () => {
  const free: PaymentProduct = { ...freeProduct, features: { ...freeProduct.features, sundayTheme: false, extraMissions: false } }
  const premium: PaymentProduct = { ...premiumProduct, features: { ...premiumProduct.features, sundayTheme: true, extraMissions: true } }
  const table = planComparison(free, premium)
  assert.deepEqual(table.price, { free: '0원', premium: '월 14,900원' })
  assert.deepEqual(table.groups.map(group => group.title), ['아이', '학부모'])
  assert.deepEqual(cells(table), {
    '주간 테마': ['월~토', '월~일'],
    '생각 유형별 추가 미션': [PLAN_NONE, '있음'],
    '되물음·돌아보기': ['있음', '있음'],
    '꾸미기': ['있음', '있음'],
    '일일 리포트': ['있음', '있음'],
    '주간 학습 수치': ['있음', '있음'],
    '한 주의 기록·이번 주 저녁 질문': [PLAN_NONE, '있음'],
    '대표 답변 설명': [PLAN_NONE, '있음'],
    '리포트에 물어보기': [PLAN_NONE, '하루 30회'],
    '추억 그림책': ['최근 4주 표지 보기', '전체 보기 + 발급 하루 3권'],
  })
  const book = table.groups[1].rows.find(row => row.label === '추억 그림책')
  assert.equal(book?.note, '한 주를 엮은 그림책')
  assert.equal(JSON.stringify(table).includes('AI 관찰'), false)
})

test('#998 비교표: 상품 값이 없으면 core 규칙과 같게 유료 상품에만 제공으로 본다', () => {
  const bare = (price: number): PaymentProduct => ({ ...premiumProduct, price, features: {}, limits: {} })
  const table = cells(planComparison(bare(0), bare(9900)))
  assert.deepEqual(table['주간 테마'], ['월~토', '월~일'])
  assert.deepEqual(table['생각 유형별 추가 미션'], [PLAN_NONE, '있음'])
  assert.deepEqual(table['리포트에 물어보기'], [PLAN_NONE, '있음'])
  assert.deepEqual(table['추억 그림책'], [MEMORY_BOOK_FREE, '전체 보기 + 발급'])
})

test('#998 비교표: 한도 0·잘못된 값·꺼진 기능은 숫자를 붙이지 않는다', () => {
  const premium = (features: Record<string, unknown>, limits: Record<string, unknown>): PaymentProduct => ({ ...premiumProduct, features, limits })
  assert.deepEqual(cells(planComparison(freeProduct, premium({ memoryBook: true }, { dailyMemoryBooks: 0, dailyConversations: 0 })))['추억 그림책'], [MEMORY_BOOK_FREE, '전체 보기'])
  assert.deepEqual(cells(planComparison(freeProduct, premium({ memoryBook: true }, { dailyMemoryBooks: 2.5 })))['추억 그림책'], [MEMORY_BOOK_FREE, '전체 보기 + 발급'])
  assert.deepEqual(cells(planComparison(freeProduct, premium({ memoryBook: false }, { dailyMemoryBooks: 3 })))['추억 그림책'], [MEMORY_BOOK_FREE, MEMORY_BOOK_FREE])
  assert.deepEqual(cells(planComparison(freeProduct, premium({}, { dailyConversations: 0 })))['리포트에 물어보기'], [PLAN_NONE, PLAN_NONE])
  // 무료 상품은 하루 권 수 값이 있어도 memoryBook이 꺼져 있으면 제공하지 않는다(목업 무료 상품 limits.dailyMemoryBooks = 3)
  assert.deepEqual(cells(planComparison(freeProduct, premiumProduct))['추억 그림책'], [MEMORY_BOOK_FREE, '전체 보기 + 발급 하루 3권'])
})

test('#998 비교표 상품: 활성 무료 하나와 활성 월 결제 유료 하나가 모두 있어야 한다', () => {
  assert.deepEqual(comparisonProducts([premiumProduct, freeProduct]), { free: freeProduct, premium: premiumProduct })
  assert.equal(comparisonProducts([premiumProduct]), null)
  assert.equal(comparisonProducts([freeProduct, { ...premiumProduct, active: false }]), null)
  assert.equal(comparisonProducts([freeProduct, { ...premiumProduct, billingCycle: 'YEARLY' }]), null)
})
