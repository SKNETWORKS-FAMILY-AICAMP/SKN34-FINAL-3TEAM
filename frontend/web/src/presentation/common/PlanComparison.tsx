import { Check, Lock } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router'
import { paymentApi } from '../../data/payment/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { PLAN_INCLUDED, PLAN_NONE, comparisonProducts, planComparison } from '../../domain/planComparison.ts'
import './planComparison.css'

/**
 * 무료·프리미엄 비교표(P13, #998). 학부모 이용권·결제 화면(`id="plan-compare"`)과 로그인 전 이용 안내에서 쓴다.
 * 아이 화면에는 두지 않는다(FN-DSH-01). 상품은 공개 API `GET /products`에서 읽는다.
 */
export function PlanComparison({ id, heading: Heading = 'h2' }: { id?: string; heading?: 'h2' | 'h3' }) {
  const products = useParentQuery(['products'], signal => paymentApi.products(signal))
  const pair = products.data ? comparisonProducts(products.data.items) : null
  const table = pair ? planComparison(pair.free, pair.premium) : null
  const section = useRef<HTMLElement>(null)
  const { hash } = useLocation()
  const ready = !!table
  // 다른 화면에서 #plan-compare로 들어오면 표가 그려진 뒤 그 위치로 옮긴다(상품은 비동기로 온다).
  // 붙어 있는 위쪽 머리글만큼의 여백은 CSS(--parent-topbar-height)가 맡는다.
  useEffect(() => {
    if (id && ready && hash === `#${id}`) section.current?.scrollIntoView?.({ block: 'start' })
  }, [id, hash, ready])
  const titleId = id ? `${id}-title` : undefined
  return <section className="plan-compare" id={id} ref={section} aria-labelledby={titleId} aria-label={titleId ? undefined : '무료·프리미엄 비교'}>
    <Heading id={titleId}>무료·프리미엄 비교</Heading>
    {products.isPending && <p role="status">비교표를 불러오고 있어요.</p>}
    {products.isError && <p role="alert">상품 정보를 불러오지 못했어요. <button type="button" onClick={() => { void products.refetch() }}>다시 불러오기</button></p>}
    {products.data && !table && <p>지금 비교할 수 있는 이용권 정보가 없어요.</p>}
    {table && <table className="plan-compare-table">
      <thead><tr><th scope="col">기능</th><th scope="col">무료<small className="plan-compare-price">{table.price.free}</small></th><th scope="col" className="plan-compare-premium">프리미엄<small className="plan-compare-price">{table.price.premium}</small></th></tr></thead>
      {table.groups.map(group => <tbody key={group.title}>
        <tr className="plan-compare-group"><th scope="rowgroup" colSpan={3}>{group.title}</th></tr>
        {group.rows.map(row => <tr key={row.label} className={row.free === row.premium ? 'plan-compare-same' : 'plan-compare-diff'}>
          <th scope="row">{row.label}{row.note && <small>{row.note}</small>}</th>
          <td><Cell value={row.free} /></td><td className="plan-compare-premium"><Cell value={row.premium} /></td>
        </tr>)}
      </tbody>)}
    </table>}
  </section>
}

/** 없음은 자물쇠, 있음은 체크 아이콘으로 보이고 화면 읽기 프로그램에는 "없음"·"있음"으로 읽힌다. 횟수·요일 같은 값은 글자 그대로. */
function Cell({ value }: { value: string }) {
  if (value === PLAN_NONE) return <span className="plan-compare-none"><Lock size={14} aria-hidden="true" /><span className="plan-compare-hidden">없음</span></span>
  if (value === PLAN_INCLUDED) return <span className="plan-compare-yes"><Check size={18} strokeWidth={3} aria-hidden="true" /><span className="plan-compare-hidden">있음</span></span>
  return <strong className="plan-compare-amount">{value}</strong>
}
