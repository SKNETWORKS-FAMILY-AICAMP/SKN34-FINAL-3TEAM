import type { PaymentProduct } from './payment.ts'

type Product = Pick<PaymentProduct, 'price' | 'features' | 'limits'>
export interface PlanComparisonRow { label: string; note?: string; free: string; premium: string }
export interface PlanComparisonGroup { title: string; rows: PlanComparisonRow[] }

export const PLAN_NONE = '–'
const NONE = PLAN_NONE, INCLUDED = '있음'
const won = (n: number) => n.toLocaleString('ko-KR') + '원'

/** core `ProductEntitlementService`와 같은 규칙: 값이 없으면 유료 상품(구독)만 제공, 불리언이면 그 값. */
function enabled(product: Product, key: string) {
  const value = product.features[key]
  return typeof value === 'boolean' ? value : product.price > 0
}
/** 하루 한도: 0 이상 정수면 그 값, 아니면 null(값 없음). */
function dailyLimit(product: Product, key: string) {
  const value = product.limits[key]
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
}
function feature(product: Product, key: string, label: (yes: boolean) => string) {
  return label(enabled(product, key))
}
/** 하루 횟수 칸: 한도가 있으면 "하루 N단위"(0이면 없음), 값이 없으면 유료 상품만 "있음". */
function limited(product: Product, key: string, unit: string, featureKey?: string) {
  if (featureKey && !enabled(product, featureKey)) return NONE
  const limit = dailyLimit(product, key)
  if (limit === null) return product.price > 0 ? INCLUDED : NONE
  return limit === 0 ? NONE : `하루 ${limit}${unit}`
}

/**
 * 무료·프리미엄 비교표(P13, #998). 지금 구현된 기능만 싣는다. 상품 데이터 칸은
 * 가격·`features.sundayTheme`·`features.extraMissions`·`limits.dailyConversations`·`features.memoryBook`+`limits.dailyMemoryBooks`,
 * 나머지는 고정 문구다.
 */
export function planComparison(free: Product, premium: Product): { price: { free: string; premium: string }; groups: PlanComparisonGroup[] } {
  const both = (label: string, note?: string): PlanComparisonRow => ({ label, note, free: INCLUDED, premium: INCLUDED })
  const paidOnly = (label: string, note?: string): PlanComparisonRow => ({ label, note, free: NONE, premium: INCLUDED })
  const row = (label: string, cell: (p: Product) => string, note?: string): PlanComparisonRow => ({ label, note, free: cell(free), premium: cell(premium) })
  return {
    price: { free: won(free.price), premium: `월 ${won(premium.price)}` },
    groups: [
      { title: '아이', rows: [
        row('주간 테마', p => feature(p, 'sundayTheme', yes => yes ? '월~일' : '월~토')),
        row('생각 유형별 추가 미션', p => feature(p, 'extraMissions', yes => yes ? INCLUDED : NONE)),
        both('되물음·돌아보기'),
        both('꾸미기'),
      ] },
      { title: '학부모', rows: [
        both('일일 리포트'),
        both('주간 학습 수치'),
        paidOnly('한 주의 기록·이번 주 저녁 질문'),
        paidOnly('대표 답변 설명'),
        row('리포트에 물어보기', p => limited(p, 'dailyConversations', '회')),
        row('추억 그림책', p => limited(p, 'dailyMemoryBooks', '권', 'memoryBook'), '한 주를 엮은 그림책'),
      ] },
    ],
  }
}

/** 비교표에 쓸 상품: 활성 무료(0원) 하나와 활성 월 결제 유료 하나. 둘 중 하나라도 없으면 null. */
export function comparisonProducts<T extends PaymentProduct>(items: T[]): { free: T; premium: T } | null {
  const free = items.find(p => p.active && p.price === 0)
  const premium = items.find(p => p.active && p.price > 0 && p.billingCycle === 'MONTHLY')
  return free && premium ? { free, premium } : null
}
