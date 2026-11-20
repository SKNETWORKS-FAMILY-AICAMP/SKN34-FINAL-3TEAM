import { lazy, Suspense, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { serviceApi } from '../../data/serviceApi.ts'
import { supportApi } from '../../data/support/api.ts'
import type { InquiryCategory, SupportTarget } from '../../domain/service.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { formatKoreanDateTime } from '../common/dateTime.ts'
import { supportStatusLabel, supportCategoryLabel, supportTargetLabel } from '../support/supportLabels.ts'
import './service.css'
const NotificationCenter = lazy(() => import('./NotificationCenter.tsx').then(module => ({ default: module.NotificationCenter })))

export function ServiceCenter({ page }: { page: 'help' | 'support' | 'notices' | 'notifications' }) {
  const { session } = useSession()
  const role = session!.role
  const root = '/' + role.toLowerCase()
  const nav = [{ path: root + '/home', label: '시작 화면' }, { path: root + '/help', label: '이용 도움말' }, { path: root + '/support', label: '문의·오류 신고' }, { path: root + '/notices', label: '공지·점검' },
    ...(role === 'ADMIN' ? [] : [{ path: root + '/support/results', label: '신고·문의 처리 결과' }])]
  return <Workspace title="사고뭉치 이용 안내" nav={nav}>
    <ServiceContent page={page} />
  </Workspace>
}
export function ServiceContent({ page }: { page: 'help' | 'support' | 'notices' | 'notifications' }) {
  const { session } = useSession()
  const role = session!.role
  return <div className="svc-page">{page === 'help' ? <Help role={role} /> : page === 'notices' ? <Notices /> : page === 'notifications' ? <Suspense fallback={<p role="status">알림을 불러오고 있습니다.</p>}><NotificationCenter role={role} /></Suspense> : <Support />}</div>
}
export function Help({ role }: { role: string }) {
  const q = useParentQuery(['help', role], signal => serviceApi.help(role, signal))
  const root = '/' + role.toLowerCase()
  return <section className="service-help"><header className="parent-page-head"><h1>이용 도움말</h1><p>학습 기록을 읽는 방법과 이용 안내를 확인하세요.</p></header><QueryFeedback query={q} />
    <div className="service-reading-list">{q.data?.items.map(item => <details key={item.title}><summary>{role === 'PARENT' && item.title === '수치와 분석의 한계' ? '학습 수치와 분석은 어떻게 읽어야 하나요?' : item.title}</summary><div className="service-reading-body"><p>{item.body}</p></div></details>)}</div>
    {q.data && !q.data.items.length && <p>등록된 도움말이 없습니다.</p>}
    <footer className="service-help-footer"><div><h2>더 확인할 내용이 있나요?</h2><p>문의하거나 이미 접수한 내용을 확인할 수 있어요.</p></div><div><Link to={root + '/support'}>문의하기</Link>{role !== 'ADMIN' && <Link to={root + '/support/results'}>내 접수 내역 보기</Link>}</div></footer>
  </section>
}
export function Notices() {
  const q = useParentQuery(['notices'], serviceApi.notices)
  const [kind, setKind] = useState(''), [search, setSearch] = useState(''), [page, setPage] = useState(0)
  const rows = (q.data?.items ?? []).filter(n => (!kind || n.kind === kind) && n.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())).sort((a,b) => b.visibleFrom.localeCompare(a.visibleFrom))
  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / 10) - 1))
  return <section className="service-notices"><header className="parent-page-head"><h1>공지·점검 안내</h1></header><QueryFeedback query={q} />
    <div className="service-list-tools"><div className="service-filter-tabs" aria-label="공지 종류">{[['','전체'],['NOTICE','일반 공지'],['MAINTENANCE','점검']].map(([value,label]) => <button key={value} aria-pressed={kind === value} onClick={() => {setKind(value);setPage(0)}}>{label}</button>)}</div><input aria-label="공지 제목 검색" placeholder="제목으로 찾기" value={search} onChange={e => {setSearch(e.target.value);setPage(0)}} /></div>
    {q.data && !rows.length && <div className="service-empty">{q.data.items.length ? '조건에 맞는 공지가 없습니다.' : '현재 공개된 공지가 없습니다.'}</div>}
    <div className="service-reading-list">{rows.slice(currentPage * 10, (currentPage + 1) * 10).map(n => <details key={n.noticeId}><summary><span className="service-kind" data-kind={n.kind}>{n.kind === 'MAINTENANCE' ? '점검' : '공지'}</span><strong>{n.title}</strong><time dateTime={n.visibleFrom}>{formatKoreanDateTime(n.visibleFrom)}</time></summary><div className="service-reading-body"><p>{n.body}</p><small>게시 기간 · {formatKoreanDateTime(n.visibleFrom)} ~ {n.visibleTo ? formatKoreanDateTime(n.visibleTo) : '종료일 미정'}</small></div></details>)}</div>
    {rows.length > 10 && <nav className="service-pagination" aria-label="공지 페이지"><button disabled={currentPage === 0} onClick={() => setPage(currentPage-1)}>이전</button><span>{currentPage+1} / {Math.ceil(rows.length/10)}</span><button disabled={(currentPage+1)*10 >= rows.length} onClick={() => setPage(currentPage+1)}>다음</button></nav>}
  </section>
}
/** level: 학생 도움말(#648)처럼 같은 화면에 이미 h1이 있으면 h2로 그린다 */
export function Support({ level = 'h1' }: { level?: 'h1' | 'h2' } = {}) {
  const [params] = useSearchParams()
  // 같은 화면에서 다른 신고 대상이나 일반 문의로 이동해도 이전 대상이 남지 않게 한다.
  return <SupportForm key={JSON.stringify([params.get('targetType'), params.get('targetId')])} level={level} />
}
function SupportForm({ level }: { level: 'h1' | 'h2' }) {
  const Title = level, Sub = level === 'h1' ? 'h2' : 'h3'
  const [params] = useSearchParams()
  const [kind, setKind] = useState<'error-reports' | 'inquiries'>(params.has('targetId') ? 'error-reports' : 'inquiries')
  const [targetType, setTargetType] = useState<SupportTarget>((['FOLLOWUP','JUDGMENT','ANALYSIS','REPORT'].includes(params.get('targetType') ?? '') ? params.get('targetType') : 'JUDGMENT') as SupportTarget)
  const [targetId, setTargetId] = useState(params.get('targetId') ?? '')
  const [category, setCategory] = useState(params.has('targetId') ? 'OTHER' : 'USAGE'), [title, setTitle] = useState(''), [comment, setComment] = useState(''), [notice, setNotice] = useState('')
  // 같은 신고 내용을 다시 보내면 같은 Idempotency-Key를 써서 중복 접수를 막는다.
  const keys = useRef(new Map<string, string>())
  const reports = useParentQuery(['support', 'error-reports'], supportApi.reports, kind === 'error-reports')
  const inquiries = useParentQuery(['support', 'inquiries'], supportApi.inquiries, kind === 'inquiries')
  const submit = useParentMutation(async () => {
    if (kind === 'inquiries') return supportApi.submitInquiry({ category: category as InquiryCategory, title: title.trim(), body: comment })
    const data = { targetType, targetId: targetId.trim(), category, comment }
    const body = JSON.stringify(data), key = keys.current.get(body) ?? crypto.randomUUID()
    keys.current.set(body, key)
    return supportApi.submitReport(data, key)
  })
  const q = kind === 'error-reports' ? reports : inquiries
  return <section className="service-support"><Title>문의·오류 신고</Title><p>일반 이용 문의와 학습 결과 오류를 구분해서 접수합니다. 접수만으로 판정이나 답변이 바뀌지는 않습니다.</p>
    <div className="ws-actions support-kind-tabs"><button aria-pressed={kind === 'inquiries'} onClick={() => { setKind('inquiries'); setCategory('USAGE') }}>이용 중 궁금한 점이 있어요</button><button aria-pressed={kind === 'error-reports'} onClick={() => { setKind('error-reports'); setCategory('OTHER') }}>학습 결과가 이상해요</button></div>
    <form className="ws-form ws-card support-compose" onSubmit={e => { e.preventDefault(); if (kind === 'error-reports' && !targetId.trim()) return; void submit.mutateAsync(undefined).then(() => { keys.current.clear(); setNotice('접수했습니다. 아래 목록에서 처리 상태를 확인하실 수 있습니다.'); setTitle(''); setComment('') }).catch(() => {}) }}>
      {kind === 'error-reports' && <><p role="note">{targetId ? `${supportTargetLabel(targetType)} 기록이 신고 대상으로 연결되어 있습니다.` : '신고할 결과 화면에서 오류 신고를 누르면 대상 기록이 자동으로 연결됩니다. 기록을 찾기 어려우면 일반 문의로 접수해 주세요.'}</p><details><summary>신고 대상 확인·직접 입력</summary><div className="ws-form"><label>신고 대상<select value={targetType} onChange={e => { setTargetType(e.target.value as SupportTarget); setTargetId('') }}>{[['JUDGMENT','판정'],['FOLLOWUP','되묻기'],['ANALYSIS','분석 대화'],['REPORT','리포트']].map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label><label>대상 기록 번호<input value={targetId} onChange={e => setTargetId(e.target.value)} maxLength={200}/></label></div></details></>}
      <label>유형<select value={category} onChange={e => setCategory(e.target.value)}>{(kind === 'error-reports' ? [['WRONG_JUDGMENT','판정이 틀려요'],['ODD_QUESTION','질문이 이상해요'],['MISMATCH','숫자·인용이 달라요'],['INAPPROPRIATE','부적절한 표현'],['OTHER','기타']] : [['ACCOUNT','계정'],['USAGE','이용 방법'],['PAYMENT','결제']]).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      {kind === 'inquiries' && <label>제목<input required value={title} onChange={e => setTitle(e.target.value)} maxLength={200}/></label>}
      <label>내용<textarea required minLength={2} maxLength={2000} value={comment} onChange={e => setComment(e.target.value)} /></label><small>비밀번호·카드 정보·실제 아동 개인정보는 적지 마세요.</small>
      <button className="cj-primary" disabled={submit.isPending || !comment.trim() || (kind === 'error-reports' ? !targetId.trim() : !title.trim())}>접수하기</button><ErrorNotice error={submit.error} /><p role="status">{notice}</p>
    </form><Sub>내 접수 내역</Sub><QueryFeedback query={q} />{q.data && !q.data.items.length && <p>접수한 내역이 없습니다.</p>}
    <div className="service-reading-list support-history">{kind === 'error-reports'
      ? reports.data?.items.map(r => <details key={r.reportId}><summary><span className="service-kind">{supportStatusLabel(r.status)}</span><strong>{supportCategoryLabel(r.category)}</strong><time>{formatKoreanDateTime(r.createdAt)}</time></summary><div className="service-reading-body"><h3>접수한 내용</h3><p>{r.comment}</p>{r.targetId && <small>신고 대상 · {supportTargetLabel(r.targetType)}</small>}<div className="support-answer"><h3>처리 답변</h3><p>{r.reviewReason ?? '아직 처리 결과가 등록되지 않았습니다.'}</p></div></div></details>)
      : inquiries.data?.items.map(i => <details key={i.inquiryId}><summary><span className="service-kind">{supportStatusLabel(i.status)}</span><strong>{i.title}</strong><time>{formatKoreanDateTime(i.createdAt)}</time></summary><div className="service-reading-body"><small>{supportCategoryLabel(i.category)}</small><h3>접수한 내용</h3><p>{i.body}</p><div className="support-answer"><h3>처리 답변</h3><p>{i.answer ?? '아직 처리 결과가 등록되지 않았습니다.'}</p></div></div></details>)}</div></section>
}
