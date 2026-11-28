import { knownEntitlement, useChildEntitlement } from '../../data/payment/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { Link } from 'react-router'

/** Resolve capabilities on the server; an absent subscription does not imply a free product. */
export function EntitlementSummary({ childId, report = false }: { childId: string; report?: boolean }) {
  const query = useChildEntitlement(childId)
  const entitlement = knownEntitlement(query)
  return <>
    <QueryFeedback query={query} />
    {entitlement && (report ? entitlement.narrativeEnabled ? <p>이용권에 리포트 요약·근거 인용이 포함됩니다.</p>
      : entitlement.refundPending ? <p>환불 검토 중에는 수치 리포트를 볼 수 있어요. 요약·근거 설명은 이용이 제한됩니다.</p>
      : entitlement.status === 'FREE' ? <div className="report-plan-preview"><p>무료로 학습 수치를 확인할 수 있어요. 프리미엄에서는 한 주의 기록, 저녁 질문과 대표 답변의 근거 설명도 함께 읽을 수 있어요.</p><Link className="cj-secondary premium-compare-link" to={`/parent/billing?childId=${encodeURIComponent(childId)}#plan-compare`}>무료·프리미엄 비교 및 이용권 보기 →</Link></div>
      : <p>현재 이용권에서는 수치 리포트를 볼 수 있어요. 이용권·결제에서 요약·근거 설명의 이용 상태를 확인해 주세요.</p>
      : <>
        <strong>{entitlement.product.name}</strong>
        <small>{entitlement.refundPending ? '환불 검토 중 · 유료 기능 이용 제한' : entitlement.status === 'FREE' ? '무료 이용권' : '구독 이용권'}</small>
        {Object.entries({ dailyMissions: '하루 미션', dailyFeedback: '하루 피드백', dailyConversations: '하루 기록에 물어보기' }).map(([key, label]) => {
          const limit = entitlement.product.limits[key]
          return typeof limit === 'number' && Number.isInteger(limit) && limit >= 0
            ? <small key={key}>{label} {limit}회</small> : null
        })}
      </>)}
  </>
}

/** 짧은 이용권 이름(학습 시작 카드). 조회 전·실패는 무료로 가정하지 않는다. */
export function EntitlementName({ childId }: { childId: string }) {
  const query = useChildEntitlement(childId), entitlement = knownEntitlement(query)
  return <>{entitlement ? entitlement.product.name : query.isPending ? '이용권 확인 중' : '이용권 확인 필요'}</>
}
