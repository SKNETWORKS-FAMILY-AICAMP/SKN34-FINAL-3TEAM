import { useModelLoading } from '../../data/admin/queries.ts'

export function ModelLoadingStatus({ name, version, revision }: { name: string; version: string; revision: number }) {
  const q = useModelLoading()
  if (q.isPending) return <div>Pod 로딩 보고 조회 중</div>
  if (q.isError) return <div role="alert">로딩 보고를 조회하지 못했습니다. 로딩 성공 여부는 알 수 없습니다.<button onClick={() => void q.refetch()}>다시 조회</button></div>
  const summary = q.data.summaries.find(s => s.name === name && s.version === version && s.revision === revision)
  return <div aria-label={`${name} Pod 로딩 상태`}>
    <p>{summary?.observedPods ? `최근 보고 Pod ${summary.observedPods}개 중 로딩 완료 ${summary.loadedPods}개` : '최근 Pod 보고 없음 · 로딩 여부 미확인'}</p>
    <p>최근 보고된 Pod 기준이며 전체 배포 Pod 수는 아닙니다. {q.data.staleAfterSeconds}초 이상 보고가 없으면 집계에서 제외합니다.</p>
    <ul>{q.data.pods.map(p => {
      const m = p.models.find(m => m.name === name)
      const matches = m?.version === version && m.revision === revision
      const status = p.stale ? '보고 만료' : !matches ? '대상 버전 보고 대기' : m.status === 'LOADED' ? '로딩 완료' : m.status === 'FAILED' ? '로딩 실패' : '로딩 중'
      return <li key={p.instanceId}><strong>{p.podId}: {status}</strong>{!p.stale && matches && m.status === 'FAILED' && <> · {m.errorType} · {m.previousModelRetained ? `기존 모델 유지 (${m.loadedVersion}, revision ${m.loadedRevision})` : '기존 모델 없음'}</>} · 마지막 보고 {new Date(p.reportedAt).toLocaleString()}</li>
    })}</ul>
    <p>로딩 완료는 품질 승인이나 추론 검증 완료를 뜻하지 않습니다.</p>
  </div>
}
