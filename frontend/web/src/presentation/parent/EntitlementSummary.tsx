import { knownEntitlement, useChildEntitlement } from '../../data/payment/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'

/** Resolve capabilities on the server; an absent subscription does not imply a free product. */
export function EntitlementSummary({ childId, report = false }: { childId: string; report?: boolean }) {
  const query = useChildEntitlement(childId)
  const entitlement = knownEntitlement(query)
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

/** 짧은 이용권 이름(학습 시작 카드). 조회 전·실패는 무료로 가정하지 않는다. */
export function EntitlementName({ childId }: { childId: string }) {
  const query = useChildEntitlement(childId), entitlement = knownEntitlement(query)
  return <>{entitlement ? entitlement.product.name : query.isPending ? '이용권 확인 중' : '이용권 확인 필요'}</>
}
