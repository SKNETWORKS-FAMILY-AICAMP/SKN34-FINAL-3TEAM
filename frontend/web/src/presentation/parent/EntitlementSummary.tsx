import { paymentApi } from '../../data/payment/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'

/** Resolve capabilities on the server; an absent subscription does not imply a free product. */
export function EntitlementSummary({ childId, report = false }: { childId: string; report?: boolean }) {
  const query = useParentQuery(['entitlement', childId], signal => paymentApi.entitlement(childId, signal))
  const entitlement = !query.error ? query.data : undefined
  return <>
    <QueryFeedback query={query} />
    {entitlement && (report ? <p>{entitlement.narrativeEnabled
      ? '이용권에 리포트 요약·근거 인용이 포함됩니다. 실제 제공 범위는 학생의 공개 설정에 따라 달라집니다.'
      : '현재 이용권에서는 리포트 수치를 제공합니다. 요약·근거 인용은 제공하지 않습니다.'}</p>
      : <>
        <strong>{entitlement.product.name}</strong>
        <small>{entitlement.refundPending ? '환불 검토 중 · 유료 기능 이용 제한' : entitlement.status === 'FREE' ? '무료 이용권' : '구독 이용권'}</small>
        {Object.entries({ dailyMissions: '하루 미션', dailyFeedback: '하루 피드백', dailyConversations: '하루 분석 대화' }).map(([key, label]) => {
          const limit = entitlement.product.limits[key]
          return typeof limit === 'number' && Number.isInteger(limit) && limit >= 0
            ? <small key={key}>{label} {limit}회</small> : null
        })}
      </>)}
  </>
}
