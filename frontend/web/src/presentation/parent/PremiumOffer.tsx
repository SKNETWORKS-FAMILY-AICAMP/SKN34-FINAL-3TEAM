import { ArrowUpRight, BookOpen, Check, UsersRound } from 'lucide-react'
import { Link } from 'react-router'
import type { Ref } from 'react'
import type { PaymentProduct } from '../../domain/payment.ts'
import { PLAN_INCLUDED, PLAN_NONE, planComparison } from '../../domain/planComparison.ts'
import './premium-offer.css'

export function PremiumOffer({ product, childName, subscribed, current, disabled, busy, opening, paymentAvailable, onCheckout }: {
  product: PaymentProduct; childName?: string; subscribed: boolean; current: boolean; disabled: boolean; busy: boolean; opening: boolean; paymentAvailable: boolean; onCheckout: () => void
}) {
  // Reuse the established plan rules; only the premium column is displayed here.
  const groups = planComparison(product, product).groups
  return <section className="premium-offer" aria-label={product.name.endsWith('이용권') ? product.name : `${product.name} 이용권`}>
    <div className="premium-purchase">
      <div className="premium-price-panel">
        <h2>{product.name}</h2>
        <p className="premium-duration">자녀 {product.childLimit}명 · 1개월 이용권</p>
        <div className="premium-price"><strong>{product.price.toLocaleString('ko-KR')}<span>원</span></strong><span>/ 1개월</span></div>
      </div>
      {subscribed ? <a className="premium-checkout" href="#current-subscriptions">현재 구독 관리<ArrowUpRight size={19} aria-hidden="true" /></a>
        : <button className="premium-checkout" disabled={disabled || !paymentAvailable} onClick={onCheckout}>{!paymentAvailable ? '결제 준비 중' : busy ? '주문 준비 중…' : opening ? '새 탭에서 결제 진행 중' : '결제수단 선택'}{paymentAvailable && <ArrowUpRight size={19} aria-hidden="true" />}</button>}
      <p className="premium-child">{childName ? `${childName}의 이용권` : '화면 위에서 이용할 자녀를 선택해 주세요.'}{current && <span>이용 중</span>}</p>
      {subscribed && !current && <p className="premium-payment-note">이용 중인 구독이 끝난 뒤 구매할 수 있어요.</p>}
      <p className="premium-payment-note">1개월 단건 구매이며,<br />자동 갱신은 별도 동의 후 설정해요.</p>
      {!subscribed && !paymentAvailable && <p className="premium-payment-note" role="note">지금 결제를 이용할 수 없어요. <Link to="/parent/support">결제 문의하기</Link></p>}
    </div>
    <div className="premium-benefits">
      {groups.map((group, index) => <section key={group.title} className="premium-benefit-group">
        <h3>{index === 0 ? <BookOpen size={21} aria-hidden="true" /> : <UsersRound size={21} aria-hidden="true" />}{group.title === '아이' ? '아이의 생각을 넓히는 활동' : '학부모와 함께 보는 기록'}</h3>
        <ul>{group.rows.filter(row => row.premium !== PLAN_NONE).map(row => <li key={row.label}><Check size={17} aria-hidden="true" /><span>{row.label}{row.premium !== PLAN_INCLUDED && <small>{row.premium}</small>}</span></li>)}</ul>
      </section>)}
    </div>
  </section>
}

// Visual price proposals supplied by the user. These are never PaymentProducts or checkout inputs.
const proposedPrices = [9900, 12900, 14900, 19900] as const

export function PremiumPlanPreview({ headingRef, onClose }: { headingRef: Ref<HTMLHeadingElement>; onClose: () => void }) {
  return <section id="plan-change-preview" className="premium-preview" aria-labelledby="plan-change-title" aria-describedby="plan-change-note">
    <div className="premium-catalog-heading"><h2 id="plan-change-title" ref={headingRef} tabIndex={-1}>이용권 변경</h2><button type="button" onClick={onClose}>목록 닫기</button></div>
    <p id="plan-change-note" className="premium-preview-note">가격 미확정 시안이에요. 실제 이용권 변경이나 결제로 연결되지 않아요.</p>
    <ul className="premium-preview-grid">
      {proposedPrices.map((price, index) => <li key={price}>
        <div className="premium-preview-panel" data-tone={index}>
          <h3>프리미엄</h3><span className="premium-preview-label">가격 후보</span>
          <p className="premium-preview-price"><strong>{price.toLocaleString('ko-KR')}<span>원</span></strong><span>/ 1개월</span></p>
        </div>
        <button type="button" className="premium-preview-action" disabled aria-label={`${price.toLocaleString('ko-KR')}원 이용권 변경 · 시안`}>변경하기</button>
        <p className="premium-preview-benefit">동일한 프리미엄 혜택</p>
      </li>)}
    </ul>
  </section>
}
