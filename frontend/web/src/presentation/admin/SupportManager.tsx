import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { adminServiceApi as api } from '../../data/admin/serviceApi.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import type { AdminNotice, Inquiry } from '../../domain/admin/service.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Panel } from './AdminUi.tsx'
import { date } from './adminFormatting.ts'
export function SupportManager() {
  const cache=useQueryClient(), [page,setPage]=useState(0), [checkedAt]=useState(()=>Date.now())
  const inquiries = useAdminQuery(['inquiries',page], (s) => api.inquiries(page,s)), notices = useAdminQuery(['notices'], (s) => api.notices(0,s))
  const local=useAdminQuery<AdminNotice[]>(['notice-session'],async()=>cache.getQueryData<AdminNotice[]>(['admin','notice-session'])??[])
  const allNotices=[...new Map([...(notices.error?[]:notices.data?.items??[]),...(local.data??[])].map(n=>[n.noticeId,n])).values()]
  function remember(n:AdminNotice){cache.setQueryData<AdminNotice[]>(['admin','notice-session'],old=>[n,...(old??[]).filter(v=>v.noticeId!==n.noticeId)])}
  const [selected, setSelected] = useState<string | null>(null), [status, setStatus] = useState(''), [editing, setEditing] = useState<AdminNotice | 'new' | null>(null)
  const rows = inquiries.error ? [] : (inquiries.data?.items ?? []).filter((i) => !status || i.status === status)
  const chosen = rows.find((i) => i.inquiryId === selected)

  return <><div className="ad-two"><Panel title="문의"><div className="ad-toolbar"><label>문의 상태<select aria-label="문의 상태" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">현재 페이지 전체</option><option value="RECEIVED">답변 대기</option><option value="RESOLVED">답변 완료</option></select></label></div><QueryFeedback query={inquiries} />
    <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>접수</th><th>문의 제목</th><th>상태</th><th>선택</th></tr></thead><tbody>{rows.map((i) => <tr key={i.inquiryId} className={i.inquiryId === chosen?.inquiryId ? 'is-selected' : ''}><td>{date(i.createdAt)}</td><td>{i.title}<small>{{ ACCOUNT: '계정', USAGE: '이용', PAYMENT: '결제' }[i.category]}</small></td><td><Badge>{i.status === 'RESOLVED' ? '답변 완료' : '답변 대기'}</Badge></td><td><button onClick={() => setSelected(i.inquiryId)} aria-label={`${i.title} 문의 선택`}>보기</button></td></tr>)}</tbody></table></div>{!rows.length && !inquiries.isPending && <Empty />}
    {!chosen&&<Empty>문의를 선택하면 답변을 작성할 수 있습니다. 학생 원문을 자동 조회하지 않습니다.</Empty>}{chosen && <InquiryAnswer key={chosen.inquiryId} inquiry={chosen} />}
    <div className="ad-toolbar"><button disabled={!page||inquiries.isFetching} onClick={()=>{setPage(p=>p-1);setSelected(null)}}>이전 문의</button><span>{page+1}페이지</span><button disabled={inquiries.isFetching||(page+1)*20>=(inquiries.data?.totalElements??0)} onClick={()=>{setPage(p=>p+1);setSelected(null)}}>다음 문의</button></div></Panel><div className="ad-stack"><Panel title="공지·점검 안내" action={<button onClick={() => setEditing('new')}>새 공지</button>}><p className="ad-note">공개 중인 관리자 대상 공지 첫 20건과 이 로그인 세션에서 작성·수정한 공지입니다. 전체 예약·종료 공지 목록 API는 아직 제공되지 않습니다.</p><QueryFeedback query={notices} />
      <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>제목</th><th>대상</th><th>상태</th><th>관리</th></tr></thead><tbody>{!notices.error && allNotices.map((n) => <tr key={n.noticeId}><td><span>{n.title}</span><small>{date(n.visibleFrom)} ~ {date(n.visibleTo)}</small></td><td>{n.targetRoles.map((r) => r === 'PARENT' ? '학부모' : r==='ADMIN'?'관리자':'학생').join('·')}</td><td><Badge>{n.endedAt?'종료':Date.parse(n.visibleFrom)>checkedAt?'예약':n.visibleTo&&Date.parse(n.visibleTo)<checkedAt?'기간 종료':'공개'}</Badge></td><td><div className="ad-row-actions"><button onClick={() => setEditing(n)}>수정</button>{!n.endedAt && <button disabled={false} onClick={() => setEditing(n)}>종료 검토</button>}</div></td></tr>)}</tbody></table></div>
      {notices.data && !notices.error && !allNotices.length && <Empty>등록된 공지가 없습니다.</Empty>}
    </Panel>{editing && <NoticeEditor key={typeof editing === 'string' ? editing : editing.noticeId} notice={editing === 'new' ? undefined : editing} onSaved={remember} onClose={() => setEditing(null)} />}</div></div></>
}
function InquiryAnswer({ inquiry }: { inquiry: Inquiry }) {
  const [answer, setAnswer] = useState(inquiry.answer ?? ''), [notice, setNotice] = useState('')
  const save = useAdminMutation(() => api.answer(inquiry.inquiryId, answer))
  return <form className="ws-form" style={{ borderTop: '1px solid #eee', marginTop: 12, paddingTop: 16 }} onSubmit={(e) => { e.preventDefault(); void save.mutateAsync(undefined).then(() => setNotice('문의 답변을 저장했습니다.')).catch(() => {}) }}><h3>{inquiry.title}</h3><p>{inquiry.body}</p><label>답변<textarea aria-label="문의 답변" value={answer} disabled={inquiry.status==='RESOLVED'} required maxLength={4000} onChange={(e) => setAnswer(e.target.value)} /></label><div><button className="cj-primary" disabled={inquiry.status==='RESOLVED'||!answer.trim() || save.isPending}>답변 저장</button></div><p role="status">{notice}</p><ErrorNotice error={save.error} /></form>
}
function NoticeEditor({ notice, onSaved, onClose }: { notice?: AdminNotice; onSaved: (n:AdminNotice)=>void; onClose: () => void }) {
  const [today] = useState(() => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' }))
  const [title, setTitle] = useState(notice?.title ?? ''), [body, setBody] = useState(notice?.body ?? '')
  const [startsAt, setStartsAt] = useState(notice?.visibleFrom.slice(0, 10) ?? today), [endsAt, setEndsAt] = useState(notice?.visibleTo?.slice(0, 10) ?? '')
  const [roles, setRoles] = useState<AdminNotice['targetRoles']>(notice?.targetRoles ?? ['PARENT']), [message, setMessage] = useState(''), [confirmEnd, setConfirmEnd] = useState(false)
  const [kind,setKind]=useState<AdminNotice['kind']>(notice?.kind??'NOTICE')
  const save = useAdminMutation(() => api.saveNotice({kind, title:title.trim(), body:body.trim(), targetRoles:roles, visibleFrom: `${startsAt}T00:00:00+09:00`, visibleTo: endsAt?`${endsAt}T23:59:59+09:00`:null }, notice?.noticeId))
  const end = useAdminMutation(() => api.endNotice(notice!.noticeId))
  return <Panel title={notice ? '공지 수정' : '새 공지 작성'} action={<button onClick={onClose}>닫기</button>}><form className="ws-form" onSubmit={(e) => { e.preventDefault(); void save.mutateAsync(undefined).then(n => {onSaved(n);setMessage('공지를 저장했습니다.');onClose()}).catch(() => {}) }}>
    <label>구분<select aria-label="공지 구분" value={kind} onChange={e=>setKind(e.target.value as AdminNotice['kind'])}><option value="NOTICE">공지</option><option value="MAINTENANCE">점검</option></select></label><label>제목<input aria-label="공지 제목" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>내용<textarea aria-label="공지 내용" required value={body} maxLength={4000} onChange={(e) => setBody(e.target.value)} /></label>
    <fieldset><legend>공개 대상</legend>{(['PARENT', 'STUDENT','ADMIN'] as const).map((r) => <label key={r}><input type="checkbox" checked={roles.includes(r)} onChange={(e) => setRoles(e.target.checked ? [...roles, r] : roles.filter((v) => v !== r))} />{r === 'PARENT' ? '학부모' : r==='ADMIN'?'관리자':'학생'}</label>)}</fieldset>
    <div className="ad-two"><label>공개 시작일<input type="date" aria-label="공지 시작일" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} /></label><label>공개 종료일<input type="date" aria-label="공지 종료일" min={startsAt} value={endsAt} onChange={(e) => setEndsAt(e.target.value)} /></label></div>
    <div className="ws-actions"><button className="cj-primary" disabled={!roles.length || save.isPending || !!notice?.endedAt}>공지 저장</button>{notice && !notice.endedAt && <button type="button" onClick={() => setConfirmEnd(true)}>공지 종료</button>}</div><ErrorNotice error={save.error ?? end.error} /><p role="status">{message}</p>
    {confirmEnd && <div className="ad-note"><p>이 공지의 공개를 종료하시겠습니까?</p><button type="button" disabled={end.isPending} onClick={() => void end.mutateAsync(undefined).then(n=>{onSaved(n);onClose()}).catch(() => {})}>종료 확정</button> <button type="button" onClick={() => setConfirmEnd(false)}>취소</button></div>}
  </form></Panel>
}
