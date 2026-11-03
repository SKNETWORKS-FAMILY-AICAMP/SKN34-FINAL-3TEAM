import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useSession } from '../auth/sessionContext.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { serviceApi } from '../../data/serviceApi.ts'
import { supportApi } from '../../data/support/api.ts'
import type { InquiryCategory, SupportTarget } from '../../domain/service.ts'
import { notificationLabels, notificationPath } from '../../domain/service.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './service.css'

export function ServiceCenter({ page }: { page: 'help' | 'support' | 'notices' | 'notifications' }) {
  const { session } = useSession()
  const role = session!.role
  const root = '/' + role.toLowerCase()
  const nav = [{ path: root + '/home', label: '시작 화면' }, { path: root + '/help', label: '이용 도움말' }, { path: root + '/support', label: '문의·오류 신고' }, { path: root + '/notices', label: '공지·점검' },
    ...(role === 'ADMIN' ? [] : [{ path: root + '/support/results', label: '신고·문의 처리 결과' }]),
    ...(role === 'STUDENT' ? [] : [{ path: root + '/notifications', label: '알림' }])]
  return <Workspace title="사고뭉치 이용 안내" nav={nav}>
    <div className="svc-page">{page === 'help' ? <Help role={role} /> : page === 'notices' ? <Notices /> : page === 'notifications' ? <Notifications role={role} /> : <Support />}</div>
  </Workspace>
}
function Help({ role }: { role: string }) {
  const q = useParentQuery(['help', role], signal => serviceApi.help(role, signal))
  return <><h1>이용 도움말</h1><QueryFeedback query={q} />{q.data?.items.map(item => <details className="ws-card" key={item.title}><summary>{item.title}</summary><p>{item.body}</p></details>)}</>
}
function Notices() {
  const q = useParentQuery(['notices'], serviceApi.notices)
  return <><h1>공지·점검 안내</h1><QueryFeedback query={q} />{q.data && !q.data.items.length && <p>현재 공개된 공지가 없습니다.</p>}{q.data?.items.map(n => <article className="ws-card" key={n.noticeId}><h2>{n.title}</h2><p>{n.body}</p><small>{n.visibleFrom} ~ {n.visibleTo ?? '종료일 미정'}</small></article>)}</>
}
const statusLabel: Record<string, string> = { RECEIVED: '접수', IN_REVIEW: '검토 중', RESOLVED: '처리 완료' }
function Support() {
  const [params] = useSearchParams()
  const [kind, setKind] = useState<'error-reports' | 'inquiries'>(params.has('targetId') ? 'error-reports' : 'inquiries')
  const [targetType, setTargetType] = useState<SupportTarget>((['FOLLOWUP','JUDGMENT','ANALYSIS','REPORT'].includes(params.get('targetType') ?? '') ? params.get('targetType') : 'JUDGMENT') as SupportTarget)
  const [targetId, setTargetId] = useState(params.get('targetId') ?? '')
  const [category, setCategory] = useState('USAGE'), [title, setTitle] = useState(''), [comment, setComment] = useState(''), [notice, setNotice] = useState('')
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
  return <><h1>문의·오류 신고</h1><p>일반 이용 문의와 학습 결과 오류를 구분해서 접수합니다. 접수만으로 판정이나 답변이 바뀌지는 않습니다.</p>
    <div className="ws-actions"><button aria-pressed={kind === 'inquiries'} onClick={() => { setKind('inquiries'); setCategory('USAGE') }}>일반 문의</button><button aria-pressed={kind === 'error-reports'} onClick={() => { setKind('error-reports'); setCategory('OTHER') }}>판정·답변 오류</button></div>
    <form className="ws-form ws-card" onSubmit={e => { e.preventDefault(); void submit.mutateAsync(undefined).then(() => { keys.current.clear(); setNotice('접수했습니다. 아래 목록에서 처리 상태를 확인하실 수 있습니다.'); setTitle(''); setComment('') }).catch(() => {}) }}>
      {kind === 'error-reports' && <><label>신고 대상<select value={targetType} onChange={e => setTargetType(e.target.value as SupportTarget)}>{[['JUDGMENT','판정'],['FOLLOWUP','되묻기'],['ANALYSIS','분석 대화'],['REPORT','리포트']].map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label><label>대상 기록 번호<input required value={targetId} onChange={e => setTargetId(e.target.value)} maxLength={200}/></label></>}
      <label>유형<select value={category} onChange={e => setCategory(e.target.value)}>{(kind === 'error-reports' ? [['WRONG_JUDGMENT','판정이 틀려요'],['ODD_QUESTION','질문이 이상해요'],['MISMATCH','숫자·인용이 달라요'],['INAPPROPRIATE','부적절한 표현'],['OTHER','기타']] : [['ACCOUNT','계정'],['USAGE','이용 방법'],['PAYMENT','결제']]).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      {kind === 'inquiries' && <label>제목<input required value={title} onChange={e => setTitle(e.target.value)} maxLength={200}/></label>}
      <label>내용<textarea required minLength={2} maxLength={2000} value={comment} onChange={e => setComment(e.target.value)} /></label><small>비밀번호·카드 정보·실제 아동 개인정보는 적지 마세요.</small>
      <button className="cj-primary" disabled={submit.isPending || !comment.trim() || (kind === 'error-reports' ? !targetId.trim() : !title.trim())}>접수하기</button><ErrorNotice error={submit.error} /><p role="status">{notice}</p>
    </form><h2>내 접수 내역</h2><QueryFeedback query={q} />{q.data && !q.data.items.length && <p>접수한 내역이 없습니다.</p>}
    {kind === 'error-reports'
      ? reports.data?.items.map(r => <article className="ws-card" key={r.reportId}><h3>{r.category} · {statusLabel[r.status] ?? r.status}</h3><p>{r.comment}</p>{r.targetId && <small>대상 {r.targetType} · {r.targetId}</small>}<p>{r.reviewReason ?? '아직 처리 결과가 등록되지 않았습니다.'}</p><small>{r.createdAt}</small></article>)
      : inquiries.data?.items.map(i => <article className="ws-card" key={i.inquiryId}><h3>{i.category} · {statusLabel[i.status] ?? i.status}</h3><p><strong>{i.title}</strong></p><p>{i.body}</p><p>{i.answer ?? '아직 처리 결과가 등록되지 않았습니다.'}</p><small>{i.createdAt}</small></article>)}</>
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
