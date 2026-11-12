import { Link, useSearchParams } from 'react-router'
import { useSupportResults } from '../../data/support/queries.ts'
import { useSession } from '../auth/sessionContext.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

export function SupportResults() {
  const [params] = useSearchParams(), { session } = useSession()
  const reportId = params.get('reportId'), inquiryId = params.get('inquiryId')
  function detailLink(key: 'reportId' | 'inquiryId', id: string) {
    const next = new URLSearchParams(params); next.delete('reportId'); next.delete('inquiryId'); next.set(key, id)
    return '?' + next
  }
  const { reports, inquiries, detail } = useSupportResults(session, reportId, inquiryId)
  return <section className="ws-card">
    <h1>내 신고·문의 처리 결과</h1>
    <p>본인이 접수한 신고·문의의 처리 결과를 확인합니다. 신고 접수만으로 판정은 바뀌지 않습니다.</p>
    {(reports.isPending || inquiries.isPending || (detail.isEnabled && detail.isPending)) && <p role="status">불러오는 중입니다.</p>}
    <ErrorNotice error={reports.error ?? inquiries.error ?? detail.error} />
    {detail.data && <section aria-label="처리 결과">
      <p>{detail.data.status}</p>
      {'reviewReason' in detail.data ? <p>{detail.data.reviewReason ?? '아직 처리 결과가 없습니다.'}</p>
        : <><h2>{detail.data.title}</h2><p>{detail.data.body}</p><p>{detail.data.answer ?? '답변을 기다리고 있습니다.'}</p></>}
    </section>}
    <h2>내 신고</h2>
    {reports.data?.items.map(r => <p key={r.reportId}><Link to={detailLink('reportId', r.reportId)}>{r.comment || '신고'} · {r.status}</Link></p>)}
    <h2>내 문의</h2>
    {inquiries.data?.items.map(i => <p key={i.inquiryId}><Link to={detailLink('inquiryId', i.inquiryId)}>{i.title} · {i.status}</Link></p>)}
    <Link to={session?.role === 'STUDENT' ? '/student/home' : '/parent/journal'}>돌아가기</Link>
  </section>
}
