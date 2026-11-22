import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { ArrowUpRight, Megaphone, MessageSquare, Plus } from 'lucide-react'
import { adminServiceApi as api } from '../../data/admin/serviceApi.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import { noticeStatus, noticeStatusLabel, type AdminNotice, type Inquiry, type NoticeFilter, type NoticeStatus } from '../../domain/admin/service.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Inspector, Panel } from './AdminUi.tsx'
import { date } from './adminFormatting.ts'
export function SupportManager() {
  const [params,setParams] = useSearchParams()
  const tab = params.get('tab') === 'notices' ? 'notices' : 'inquiries'
  const status = params.get('status') ?? ''
  function setTab(tab: string) {
    const next=new URLSearchParams(params); next.set('tab',tab); next.delete('status'); setParams(next)
    setPage(0); setSelected(null)
  }
  function setStatus(value: string) {
    const next=new URLSearchParams(params); if(value) next.set('status',value); else next.delete('status')
    setParams(next); setPage(0); setSelected(null)
  }
  const [page,setPage] = useState(0), [noticePage,setNoticePage] = useState(0), [filter,setFilter] = useState<NoticeFilter>({})
  const inquiries = useAdminQuery(['inquiries',page,status], s => api.inquiries(page,s,status), tab==='inquiries'), notices = useAdminQuery(['notices',filter,noticePage], s => api.notices(filter,noticePage,s), tab==='notices')
  const noticeRows = notices.error ? [] : notices.data?.items ?? [], checkedAt = notices.dataUpdatedAt
  function changeFilter(next:NoticeFilter) {setFilter(next); setNoticePage(0)}
  const [selected,setSelected] = useState<string|null>(null), [editing,setEditing] = useState<AdminNotice|'new'|null>(null)
  const rows = inquiries.error ? [] : inquiries.data?.items ?? []
  const chosen = rows.find(i => i.inquiryId === selected)
  return <>
    <div className="ad-view-tabs" aria-label="문의·공지 업무"><button aria-pressed={tab === 'inquiries'} onClick={() => setTab('inquiries')}><MessageSquare size={17} aria-hidden="true" />문의함</button><button aria-pressed={tab === 'notices'} onClick={() => setTab('notices')}><Megaphone size={17} aria-hidden="true" />공지·점검</button></div>
    {tab === 'inquiries' ? <section className="ad-data-surface">
      <div className="ad-data-toolbar"><div><h2>문의</h2></div><label>문의 상태<select aria-label="문의 상태" value={status} onChange={e => setStatus(e.target.value)}><option value="">전체 상태</option><option value="RECEIVED">답변 대기</option><option value="RESOLVED">답변 완료</option></select></label></div>
      <QueryFeedback query={inquiries} />
      <div className="ad-inbox-list">{rows.map(i => <button key={i.inquiryId} className="ad-inbox-row" onClick={() => setSelected(i.inquiryId)} aria-label={`${i.title} 문의 선택`}>
        <span className={`ad-inbox-icon${i.status === 'RESOLVED' ? ' is-resolved' : ''}`}><MessageSquare size={20} aria-hidden="true" /></span><span className="ad-inbox-copy"><span className="ad-inbox-meta">{{ACCOUNT:'계정',USAGE:'이용',PAYMENT:'결제'}[i.category] ?? i.category}<span>·</span>{date(i.createdAt)}</span><strong>{i.title}</strong><span className="ad-inbox-excerpt">{i.body}</span></span><Badge active={i.status === 'RESOLVED'}>{i.status === 'RESOLVED' ? '답변 완료' : '답변 대기'}</Badge><ArrowUpRight size={17} aria-hidden="true" />
      </button>)}</div>
      {!rows.length && !inquiries.isPending && !inquiries.error && <Empty>조건에 맞는 문의가 없습니다.</Empty>}
      <div className="ad-list-footer"><span>{page+1}페이지</span><div><button disabled={!page || inquiries.isFetching} onClick={() => {setPage(p=>p-1); setSelected(null)}}>이전 문의</button><button disabled={inquiries.isFetching || (page+1)*20 >= (inquiries.data?.totalElements ?? 0)} onClick={() => {setPage(p=>p+1); setSelected(null)}}>다음 문의</button></div></div>
    </section> : <section className="ad-data-surface">
      <div className="ad-data-toolbar"><div><h2>공지·점검 안내</h2></div><button className="cj-primary" onClick={() => setEditing('new')}><Plus size={16} aria-hidden="true" />새 공지</button></div>
      <div className="ad-list-filters"><label>공지 상태<select aria-label="공지 상태" value={filter.status ?? ''} onChange={e => changeFilter({...filter,status:(e.target.value || undefined) as NoticeStatus})}><option value="">전체</option>{(Object.keys(noticeStatusLabel) as NoticeStatus[]).map(v => <option key={v} value={v}>{noticeStatusLabel[v]}</option>)}</select></label><label>공개 대상<select aria-label="공지 공개 대상" value={filter.role ?? ''} onChange={e => changeFilter({...filter,role:(e.target.value || undefined) as NoticeFilter['role']})}><option value="">전체</option>{(['PARENT','STUDENT','ADMIN'] as const).map(v => <option key={v} value={v}>{roleLabel(v)}</option>)}</select></label></div>
      <QueryFeedback query={notices} />
      <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>제목</th><th>공개 대상</th><th>상태</th><th>관리</th></tr></thead><tbody>{noticeRows.map(n => <tr key={n.noticeId}><td><strong>{n.title}</strong><small>{date(n.visibleFrom)} ~ {date(n.visibleTo)}</small></td><td>{n.targetRoles.map(roleLabel).join('·')}</td><td><Badge active={noticeStatus(n,checkedAt) === 'ACTIVE'}>{noticeStatusLabel[noticeStatus(n,checkedAt)]}</Badge></td><td><div className="ad-row-actions"><button onClick={() => setEditing(n)}>{n.endedAt ? '보기' : '수정'}</button>{!n.endedAt && <button className="ad-danger" onClick={() => setEditing(n)}>종료 검토</button>}</div></td></tr>)}</tbody></table></div>
      {notices.data && !notices.error && !noticeRows.length && <Empty>조건에 맞는 공지가 없습니다.</Empty>}
      <div className="ad-list-footer"><span>{noticePage+1}페이지</span><div><button disabled={!noticePage || notices.isFetching} onClick={() => setNoticePage(p=>p-1)}>이전 공지</button><button disabled={notices.isFetching || (noticePage+1)*20 >= (notices.data?.totalElements ?? 0)} onClick={() => setNoticePage(p=>p+1)}>다음 공지</button></div></div>
    </section>}
    {chosen && tab === 'inquiries' && <Inspector title="문의 답변" onClose={() => setSelected(null)}><InquiryAnswer key={chosen.inquiryId} inquiry={chosen} /></Inspector>}
    {editing && tab === 'notices' && <Inspector title={editing === 'new' ? '공지 작성' : '공지 검토'} onClose={() => setEditing(null)}><NoticeEditor key={typeof editing === 'string' ? editing : editing.noticeId} notice={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} /></Inspector>}
  </>
}
const roleLabel=(r:AdminNotice['targetRoles'][number])=>r==='PARENT'?'학부모':r==='ADMIN'?'관리자':'학생'
function InquiryAnswer({ inquiry }: { inquiry: Inquiry }) {
  const [answer, setAnswer] = useState(inquiry.answer ?? ''), [notice, setNotice] = useState('')
  const save = useAdminMutation(() => api.answer(inquiry.inquiryId, answer))
  return <form className="ws-form ad-inquiry-answer" onSubmit={(e) => { e.preventDefault(); void save.mutateAsync(undefined).then(() => setNotice('문의 답변을 저장했습니다.')).catch(() => {}) }}><div className="ad-message-meta"><Badge active={inquiry.status === 'RESOLVED'}>{inquiry.status === 'RESOLVED' ? '답변 완료' : '답변 대기'}</Badge><span>{date(inquiry.createdAt)}</span></div><h3>{inquiry.title}</h3><blockquote>{inquiry.body}</blockquote><label>답변<textarea aria-label="문의 답변" value={answer} disabled={inquiry.status==='RESOLVED'} required maxLength={4000} onChange={(e) => setAnswer(e.target.value)} /></label><div><button className="cj-primary" disabled={inquiry.status==='RESOLVED'||!answer.trim() || save.isPending}>답변 저장</button></div><p role="status">{notice}</p><ErrorNotice error={save.error} /></form>
}
// Saved/ended notices reappear through the server list: useAdminMutation invalidates admin queries.
function NoticeEditor({ notice, onClose }: { notice?: AdminNotice; onClose: () => void }) {
  const [today] = useState(() => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' }))
  const [title, setTitle] = useState(notice?.title ?? ''), [body, setBody] = useState(notice?.body ?? '')
  const [startsAt, setStartsAt] = useState(notice?.visibleFrom.slice(0, 10) ?? today), [endsAt, setEndsAt] = useState(notice?.visibleTo?.slice(0, 10) ?? '')
  const [roles, setRoles] = useState<AdminNotice['targetRoles']>(notice?.targetRoles ?? ['PARENT']), [message, setMessage] = useState(''), [confirmEnd, setConfirmEnd] = useState(false)
  const [kind,setKind]=useState<AdminNotice['kind']>(notice?.kind??'NOTICE')
  const save = useAdminMutation(() => api.saveNotice({kind, title:title.trim(), body:body.trim(), targetRoles:roles, visibleFrom: `${startsAt}T00:00:00+09:00`, visibleTo: endsAt?`${endsAt}T23:59:59+09:00`:null }, notice?.noticeId))
  const end = useAdminMutation(() => api.endNotice(notice!.noticeId))
  return <Panel title={notice ? '공지 수정' : '새 공지 작성'} action={<button onClick={onClose}>닫기</button>}><form className="ws-form" onSubmit={(e) => { e.preventDefault(); void save.mutateAsync(undefined).then(() => {setMessage('공지를 저장했습니다.');onClose()}).catch(() => {}) }}>
    <label>구분<select aria-label="공지 구분" value={kind} onChange={e=>setKind(e.target.value as AdminNotice['kind'])}><option value="NOTICE">공지</option><option value="MAINTENANCE">점검</option></select></label><label>제목<input aria-label="공지 제목" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>내용<textarea aria-label="공지 내용" required value={body} maxLength={4000} onChange={(e) => setBody(e.target.value)} /></label>
    <fieldset><legend>공개 대상</legend>{(['PARENT', 'STUDENT','ADMIN'] as const).map((r) => <label key={r}><input type="checkbox" checked={roles.includes(r)} onChange={(e) => setRoles(e.target.checked ? [...roles, r] : roles.filter((v) => v !== r))} />{r === 'PARENT' ? '학부모' : r==='ADMIN'?'관리자':'학생'}</label>)}</fieldset>
    <div className="ad-two"><label>공개 시작일<input type="date" aria-label="공지 시작일" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} /></label><label>공개 종료일<input type="date" aria-label="공지 종료일" min={startsAt} value={endsAt} onChange={(e) => setEndsAt(e.target.value)} /></label></div>
    <div className="ws-actions"><button className="cj-primary" disabled={!roles.length || save.isPending || !!notice?.endedAt}>공지 저장</button>{notice && !notice.endedAt && <button className="ad-danger" type="button" onClick={() => setConfirmEnd(true)}>공지 종료</button>}</div><ErrorNotice error={save.error ?? end.error} /><p role="status">{message}</p>
    {confirmEnd && <div className="ad-note"><p>이 공지의 공개를 종료하시겠습니까?</p><button className="ad-danger" type="button" disabled={end.isPending} onClick={() => void end.mutateAsync(undefined).then(onClose).catch(() => {})}>종료 확정</button> <button type="button" onClick={() => setConfirmEnd(false)}>취소</button></div>}
  </form></Panel>
}
