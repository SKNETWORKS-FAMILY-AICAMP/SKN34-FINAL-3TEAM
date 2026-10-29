import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router'
import { apiFetch } from '../../data/apiClient.ts'
import { useSession } from '../auth/sessionContext.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

type Report = { reportId: string; status: string; comment: string | null; reviewReason: string | null }
type Inquiry = { inquiryId: string; status: string; title: string; body: string; answer: string | null }
export function SupportResults() {
  const [params] = useSearchParams(), { session } = useSession()
  const reportId = params.get('reportId'), inquiryId = params.get('inquiryId')
  const reports = useQuery({ queryKey: ['support', session, 'reports'], retry: false,
    queryFn: ({ signal }) => apiFetch<{ items: Report[] }>('/error-reports', { signal }) })
  const inquiries = useQuery({ queryKey: ['support', session, 'inquiries'], retry: false,
    queryFn: ({ signal }) => apiFetch<{ items: Inquiry[] }>('/inquiries', { signal }) })
  const detail = useQuery<Report | Inquiry>({ queryKey: ['support', session, reportId, inquiryId], retry: false,
    enabled: !!reportId || !!inquiryId,
    queryFn: ({ signal }) => reportId
      ? apiFetch<Report>(`/error-reports/${encodeURIComponent(reportId)}`, { signal })
      : apiFetch<Inquiry>(`/inquiries/${encodeURIComponent(inquiryId!)}`, { signal }) })
  return <main className="ws-card">
    <h1>내 신고·문의 처리 결과</h1>
    <p>학생의 신고·문의는 본인 화면에서 결과를 확인합니다. 신고 접수만으로 판정은 바뀌지 않습니다.</p>
    {(reports.isPending || inquiries.isPending || (detail.isEnabled && detail.isPending)) && <p role="status">불러오는 중입니다.</p>}
    <ErrorNotice error={reports.error ?? inquiries.error ?? detail.error} />
    {detail.data && <section aria-label="처리 결과">
      <p>{detail.data.status}</p>
      {'reviewReason' in detail.data ? <p>{detail.data.reviewReason ?? '아직 처리 결과가 없습니다.'}</p>
        : <><h2>{detail.data.title}</h2><p>{detail.data.body}</p><p>{detail.data.answer ?? '답변을 기다리고 있습니다.'}</p></>}
    </section>}
    <h2>내 신고</h2>
    {reports.data?.items.map(r => <p key={r.reportId}><Link to={`?reportId=${r.reportId}`}>{r.comment || '신고'} · {r.status}</Link></p>)}
    <h2>내 문의</h2>
    {inquiries.data?.items.map(i => <p key={i.inquiryId}><Link to={`?inquiryId=${i.inquiryId}`}>{i.title} · {i.status}</Link></p>)}
    <Link to={session?.role === 'STUDENT' ? '/student/home' : '/parent/journal'}>돌아가기</Link>
  </main>
}
