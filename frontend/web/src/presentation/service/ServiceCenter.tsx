import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useSession } from '../auth/sessionContext.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { serviceApi } from '../../data/serviceApi.ts'
import type { SupportTarget } from '../../domain/service.ts'
import { notificationLabels, notificationPath } from '../../domain/service.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './service.css'

export function ServiceCenter({ page }: { page: 'help' | 'support' | 'notices' | 'notifications' }) {
  const { session } = useSession()
  const role = session!.role
  const root = '/' + role.toLowerCase()
  const nav = [{ path: root + '/home', label: '시작 화면' }, { path: root + '/help', label: '이용 도움말' }, { path: root + '/support', label: '문의·오류 신고' }, { path: root + '/notices', label: '공지·점검' },
    ...(role === 'STUDENT' ? [] : [{ path: root + '/notifications', label: '알림' }])]
  return <Workspace title="사고뭉치 이용 안내" nav={nav}>
    <div className="svc-page">{page === 'help' ? <Help role={role} /> : page === 'notices' ? <Notices /> : page === 'notifications' ? <Notifications role={role} /> : <Support />}</div>
  </Workspace>
}
function Help({ role }: { role: string }) {
  const q = useParentQuery(['help', role], signal => serviceApi.help(role, signal))
  return <><h1>이용 도움말</h1><QueryFeedback query={q} />{q.data?.items.map(item => <details className="ws-card" key={item.id}><summary>{item.title}</summary><p>{item.content}</p></details>)}</>
}
function Notices() {
  const q = useParentQuery(['notices'], serviceApi.notices)
  return <><h1>공지·점검 안내</h1><QueryFeedback query={q} />{q.data && !q.data.items.length && <p>현재 공개된 공지가 없습니다.</p>}{q.data?.items.map(n => <article className="ws-card" key={n.id}><h2>{n.title}</h2><p>{n.content}</p><small>{n.startsAt} ~ {n.endsAt ?? '종료일 미정'}</small></article>)}</>
}
function Support() {
  const {session}=useSession()
  const [params] = useSearchParams()
  const [kind, setKind] = useState<'error-reports' | 'inquiries'>(params.has('targetId') ? 'error-reports' : 'inquiries')
  const [targetType, setTargetType] = useState<SupportTarget>((['FOLLOWUP','JUDGMENT','ANALYSIS','REPORT'].includes(params.get('targetType') ?? '') ? params.get('targetType') : 'JUDGMENT') as SupportTarget)
  const [targetId, setTargetId] = useState(params.get('targetId') ?? '')
  const [category, setCategory] = useState('OTHER'), [comment, setComment] = useState(''), [notice, setNotice] = useState('')
  const q = useParentQuery(['cases', kind], signal => serviceApi.cases(kind, signal))
  const submit = useParentMutation(() => serviceApi.createCase(kind, { category, comment, ...(kind === 'error-reports' ? { targetType, targetId } : {}) }))
  if(session?.role==='ADMIN')return <AdminHelpdesk/>
  return <><h1>문의·오류 신고</h1><p>일반 이용 문의와 학습 결과 오류를 구분해서 접수합니다. 접수만으로 판정이나 답변이 바뀌지는 않습니다.</p>
    <div className="ws-actions"><button aria-pressed={kind === 'inquiries'} onClick={() => { setKind('inquiries'); setCategory('OTHER') }}>일반 문의</button><button aria-pressed={kind === 'error-reports'} onClick={() => { setKind('error-reports'); setCategory('OTHER') }}>판정·답변 오류</button></div>
    <form className="ws-form ws-card" onSubmit={e => { e.preventDefault(); void submit.mutateAsync(undefined).then(() => { setNotice('접수했습니다. 아래 목록에서 처리 상태를 확인하실 수 있습니다.'); setComment('') }).catch(() => {}) }}>
      {kind === 'error-reports' && <><label>신고 대상<select value={targetType} onChange={e => setTargetType(e.target.value as SupportTarget)}>{[['JUDGMENT','판정'],['FOLLOWUP','되묻기'],['ANALYSIS','분석 대화'],['REPORT','리포트']].map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label><label>대상 기록 번호<input required value={targetId} onChange={e => setTargetId(e.target.value)} maxLength={200}/></label></>}
      <label>유형<select value={category} onChange={e => setCategory(e.target.value)}>{(kind === 'error-reports' ? [['WRONG_JUDGMENT','판정이 틀려요'],['ODD_QUESTION','질문이 이상해요'],['MISMATCH','숫자·인용이 달라요'],['INAPPROPRIATE','부적절한 표현'],['OTHER','기타']] : [['ACCOUNT','계정'],['USAGE','이용 방법'],['PAYMENT','결제'],['OTHER','기타']]).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label>내용<textarea required minLength={2} maxLength={2000} value={comment} onChange={e => setComment(e.target.value)} /></label><small>비밀번호·카드 정보·실제 아동 개인정보는 적지 마세요.</small>
      <button className="cj-primary" disabled={submit.isPending || !comment.trim() || (kind === 'error-reports' && !targetId.trim())}>접수하기</button><ErrorNotice error={submit.error} /><p role="status">{notice}</p>
    </form><h2>내 접수 내역</h2><QueryFeedback query={q} />{q.data && !q.data.items.length && <p>접수한 내역이 없습니다.</p>}{q.data?.items.map(c => <article className="ws-card" key={c.id}><h3>{c.category} · {({ RECEIVED:'접수',IN_REVIEW:'검토 중',RESOLVED:'처리 완료' })[c.status]}</h3><p>{c.comment}</p>{c.targetId && <small>대상 {c.targetType} · {c.targetId}</small>}<p>{c.answer ?? '아직 처리 결과가 등록되지 않았습니다.'}</p><small>{c.createdAt}</small></article>)}</>
}
function AdminHelpdesk() {
  const {session}=useSession()
  const allowed=session?.permissions?.includes('SERVICE_OPS')
  const q=useParentQuery(['admin-inquiries'],serviceApi.adminInquiries,allowed)
  const [selected,setSelected]=useState(''),[answer,setAnswer]=useState(''),[notice,setNotice]=useState('')
  const [title,setTitle]=useState(''),[content,setContent]=useState(''),[startsAt,setStartsAt]=useState(''),[endsAt,setEndsAt]=useState(''),[role,setRole]=useState('PARENT')
  const send=useParentMutation(()=>serviceApi.answerInquiry(selected,answer))
  const publish=useParentMutation(()=>serviceApi.publishNotice({title,content,roles:[role],startsAt:new Date(startsAt).toISOString(),endsAt:endsAt?new Date(endsAt).toISOString():null}))
  if(!allowed)return <><h1>문의·공지 관리</h1><p role="alert">서비스 운영 권한이 필요합니다. 학생 원문과 결제 정보를 열람하지 않습니다.</p></>
  return <><h1>문의·공지 관리</h1><QueryFeedback query={q}/>{q.data&&!q.data.items.length&&<p>접수된 일반 문의가 없습니다.</p>}
    {q.data?.items.map(c=><article className="ws-card" key={c.id}><h2>{c.category} · {c.status}</h2><p>{c.comment}</p><p>{c.answer??'아직 답변 없음'}</p><button onClick={()=>{setSelected(c.id);setAnswer(c.answer??'')}}>이 문의 답변</button></article>)}
    {selected&&<form className="ws-card ws-form" onSubmit={e=>{e.preventDefault();void send.mutateAsync(undefined).then(()=>{setNotice('답변을 등록했습니다.');setSelected('');setAnswer('')}).catch(()=>{})}}><label>문의 답변<textarea required maxLength={2000} value={answer} onChange={e=>setAnswer(e.target.value)}/></label><button disabled={send.isPending||!answer.trim()}>답변 등록</button><ErrorNotice error={send.error}/></form>}
    <form className="ws-card ws-form" onSubmit={e=>{e.preventDefault();void publish.mutateAsync(undefined).then(()=>{setNotice('공개 기간과 대상 역할에 맞춰 공지를 등록했습니다.');setTitle('');setContent('')}).catch(()=>{})}}><h2>공지 등록</h2><label>공지 제목<input required value={title} onChange={e=>setTitle(e.target.value)}/></label><label>공지 내용<textarea required value={content} onChange={e=>setContent(e.target.value)}/></label><label>대상 역할<select value={role} onChange={e=>setRole(e.target.value)}>{['STUDENT','PARENT','ADMIN'].map(r=><option key={r}>{r}</option>)}</select></label><label>공개 시작<input type="datetime-local" required value={startsAt} onChange={e=>setStartsAt(e.target.value)}/></label><label>공개 종료 (선택)<input type="datetime-local" value={endsAt} min={startsAt} onChange={e=>setEndsAt(e.target.value)}/></label><button disabled={publish.isPending}>공지 등록</button><ErrorNotice error={publish.error}/></form><p role="status">{notice}</p></>
}
function Notifications({ role }: { role: string }) {
  const cache = useQueryClient()
  const [unread, setUnread] = useState(false), [page, setPage] = useState(0), [notice, setNotice] = useState('')
  const q = useParentQuery(['notifications', unread, page], signal => serviceApi.notifications(unread, page, signal), role !== 'STUDENT')
  const settings = useParentQuery(['notification-settings'], serviceApi.settings, role !== 'STUDENT')
  const read = useParentMutation(serviceApi.read), all = useParentMutation(serviceApi.readAll), save = useParentMutation(serviceApi.saveSettings)
  const [edited, setEdited] = useState<Record<string, boolean>>({})
  const reload = () => { void cache.invalidateQueries({ queryKey: ['parent', 'notifications'] }) }
  if (role === 'STUDENT') return <><h1>알림</h1><p>학생 전용 알림함은 제공하지 않습니다. 보호자 화면에서 확인해 주세요.</p></>
  return <><h1>알림</h1><div className="ws-actions"><label className="ws-check"><input type="checkbox" checked={unread} onChange={e => { setUnread(e.target.checked); setPage(0) }} />읽지 않은 알림만</label><button onClick={() => reload()}>새로고침</button><button disabled={all.isPending} onClick={() => void all.mutateAsync(undefined).then(reload).catch(() => {})}>모두 읽음</button></div>
    <QueryFeedback query={q} /><ErrorNotice error={read.error ?? all.error} />
    {q.data && !q.data.items.length && <p>표시할 알림이 없습니다.</p>}
    {q.data?.items.map(n => { const path = notificationPath(n.link, role, location.origin); return <article className="ws-card" key={n.id}><h2>{n.title}</h2><p>{n.readAt ? '읽음' : '읽지 않음'} · {n.createdAt}</p>{n.childId && <small>대상 자녀 {n.childId}</small>}<div className="ws-actions">{!n.readAt && <button disabled={read.isPending} onClick={() => void read.mutateAsync(n.id).then(reload).catch(() => {})}>읽음으로 표시</button>}{path ? <Link to={path}>관련 내용 열기</Link> : <p>관련 화면 주소를 확인할 수 없습니다.</p>}</div></article> })}
    <div className="ws-actions"><button disabled={!page} onClick={() => setPage(p => p-1)}>이전</button><span>{page+1}쪽</span><button disabled={!q.data?.hasNext} onClick={() => setPage(p => p+1)}>다음</button></div>
    <h2>알림 수신 설정</h2><p>앱 안 알림만 제공합니다. 이메일·푸시 발송 설정은 제공하지 않습니다.</p><QueryFeedback query={settings} />
    <form className="ws-form ws-card" onSubmit={e => { e.preventDefault(); void save.mutateAsync({ items: (settings.data?.items ?? []).map(s => ({ ...s, enabled: edited[s.type] ?? s.enabled })) }).then(() => { setEdited({}); setNotice('수신 설정을 저장했습니다.') }).catch(() => {}) }}>
      {settings.data?.items.map(s => <label className="ws-check" key={s.type}><input type="checkbox" checked={edited[s.type] ?? s.enabled} onChange={e => setEdited(v => ({ ...v, [s.type]: e.target.checked }))} />{notificationLabels[s.type]}</label>)}
      <button disabled={!settings.data || save.isPending || !Object.keys(edited).length}>설정 저장</button><ErrorNotice error={save.error} /><p role="status">{notice}</p>
    </form></>
}
