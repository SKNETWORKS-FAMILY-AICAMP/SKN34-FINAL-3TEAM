import { useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { guardianTransfers, type GuardianTransfer, type TransferRecipient } from '../../data/guardianTransfers.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentMutation, useParentQuery } from '../../data/parent/queries.ts'
import { restoreSession } from '../../data/classroom/useClassroom.ts'
import { useSession } from '../auth/sessionContext.ts'
import { ConsentFields } from '../parent/AccountForms.tsx'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { IdentityRecheck } from './AccountLifecycle.tsx'
import type { Consent } from '../../domain/parent.ts'
import { TransferDialog, guardianTransferEnabled } from './GuardianTransferUi.tsx'
import './service.css'

const labels = { PENDING: '수락 대기', ACCEPTED: '이관 완료', REJECTED: '거절됨', CANCELLED: '취소됨' }
export function GuardianTransfers() {
  const { session, setSession } = useSession()
  const canTransfer = guardianTransferEnabled && session?.nextAction !== 'CONSENT_REQUIRED'
  const children = useParentQuery(['transfer-children'], signal => parentApi.children(signal), canTransfer)
  const requests = useQuery({ queryKey: ['parent', 'guardian-transfers'], queryFn: ({ signal }) => guardianTransfers.list(signal), refetchInterval: 5000, retry: false })
  const documents = useParentQuery(['transfer-consents'], signal => parentApi.documents(signal), canTransfer)
  const [childId, setChildId] = useState(''), [email, setEmail] = useState('')
  const [recipient, setRecipient] = useState<TransferRecipient | null>(null)
  const [sendOpen, setSendOpen] = useState(false), [include, setInclude] = useState(false), [token, setToken] = useState('')
  const [accepting, setAccepting] = useState<GuardianTransfer | null>(null), [consents, setConsents] = useState<Consent[]>([])
  const [limitOpen, setLimitOpen] = useState(false), [notice, setNotice] = useState('')
  const child = children.data?.items.find(c => c.id === childId) ?? children.data?.items[0]
  const lookup = useParentMutation(guardianTransfers.recipient)
  const send = useParentMutation(() => guardianTransfers.request({ childId: child!.id, recipientId: recipient!.id, includeConversations: include }, token))
  const accept = useParentMutation(() => guardianTransfers.accept(accepting!.id, consents, token))
  const resolve = useParentMutation(({ id, reject }: { id: string; reject: boolean }) => reject ? guardianTransfers.reject(id) : guardianTransfers.cancel(id))
  function showError(error: unknown) {
    if ((error as { problem?: { code?: string } })?.problem?.code === 'CHILD_LIMIT_REACHED') setLimitOpen(true)
  }
  function close() { setSendOpen(false); setAccepting(null); setToken(''); setConsents([]) }
  async function refreshIdentity() {
    const next = await restoreSession(true)
    setSession(next)
    if (guardianTransferEnabled && next.nextAction !== 'CONSENT_REQUIRED') await children.refetch()
    await requests.refetch()
  }
  return <Workspace title="자녀 이관" nav={[{ path: '/parent/journal', label: '대시보드·공책' }, { path: '/parent/transfers', label: '자녀 이관' }]}><div className="svc-page ws-stack transfer-page"><h1>자녀 이관</h1>
    <p>{canTransfer ? '가입에 사용한 이메일로 요청을 보내고, 상대방이 수락하면 자녀가 연결됩니다.' : '지금은 기존 이관 요청의 확인·취소·거절만 할 수 있습니다. 취소만으로 탈퇴하거나 자녀가 삭제되지는 않습니다.'}</p>
    <nav><Link to="/parent/settings?section=account">계정 관리</Link> · <Link to="/parent/children/new">자녀 등록</Link></nav>
    {canTransfer && <section className="ws-card ws-form"><h2>이관 요청 보내기</h2><QueryFeedback query={children}/>
      {child ? <>
        <label>이관할 자녀<select value={child.id} onChange={e => { setChildId(e.target.value); setRecipient(null); setToken('') }}>{children.data?.items.map(c => <option key={c.id} value={c.id}>{c.nickname}</option>)}</select></label>
        <form className="ws-form" onSubmit={e => { e.preventDefault(); setRecipient(null); void lookup.mutateAsync(email.trim()).then(setRecipient).catch(showError) }}>
          <label>받는 학부모의 가입 이메일<input type="email" required value={email} onChange={e => { setEmail(e.target.value); setRecipient(null); setToken('') }} /></label>
          <button disabled={lookup.isPending}>학부모 찾기</button>
        </form>
        {recipient && <div><p>{recipient.name ?? '학부모'} · {recipient.email} · 등록 자녀 {recipient.childCount}명</p><button onClick={() => { setInclude(false); setToken(''); setSendOpen(true) }}>이관 내용 확인</button></div>}
        <ErrorNotice error={lookup.error}/>
      </> : !children.isPending && <p>등록된 자녀가 없어도 아래에서 받은 요청을 수락할 수 있습니다.</p>}
    </section>}
    <section className="ws-card ws-form"><h2>받은 요청 · 보낸 요청</h2><button onClick={() => { void refreshIdentity().catch(() => setNotice('상태를 다시 불러오지 못했습니다.')) }}>상태 새로 확인</button><QueryFeedback query={requests}/>
      {requests.data?.items.length === 0 && <p>이관 요청이 없습니다.</p>}
      {requests.data?.items.map(row => <article key={row.id} className="transfer-request"><h3>{row.direction === 'INCOMING' ? '받은 요청' : '보낸 요청'} · {labels[row.status]}</h3>
        <p>{row.childName ?? '자녀'} · {row.direction === 'INCOMING' ? `${row.senderName ?? '학부모'}님이 보냄` : `${row.recipientName ?? '학부모'}님에게 보냄`}</p>
        <p>프로필·학습 기록·리포트 포함 · 분석 상담 대화 {row.includeConversations ? '포함' : '미포함'}</p>
        {row.status === 'PENDING' && (row.direction === 'INCOMING' ? <>
          {canTransfer && <button onClick={() => { setAccepting(row); setToken(''); setConsents([]) }}>수락 내용 확인</button>}
          <button disabled={resolve.isPending} onClick={() => void resolve.mutateAsync({ id: row.id, reject: true }).catch(() => {})}>거절</button>
        </> : <button disabled={resolve.isPending} onClick={() => void resolve.mutateAsync({ id: row.id, reject: false }).catch(() => {})}>이관 요청 취소</button>)}
        {row.status === 'ACCEPTED' && <p>{row.direction === 'INCOMING' ? '자녀가 연결되었습니다. 학생 기기는 새 학부모 계정에서 다시 등록해 주세요.' : '이관한 자녀는 탈퇴 시 삭제되지 않습니다. 계정 관리에서 탈퇴 절차를 진행할 수 있습니다.'}</p>}
      </article>)}<ErrorNotice error={resolve.error}/><p role="status">{notice}</p>
    </section>
    {canTransfer && sendOpen && child && recipient && <TransferDialog title="자녀 이관을 요청하시겠습니까?">
      <p>받는 학부모: {recipient.name ?? '학부모'} / {recipient.email}</p><p>이관할 자녀: {child.nickname}</p>
      <p>자녀 프로필·학습 기록·리포트는 기본으로 이관됩니다.</p>
      <label className="ws-check"><input type="checkbox" checked={include} onChange={e => setInclude(e.target.checked)}/>내가 이 자녀에 대해 나눈 분석 상담 대화도 함께 이관합니다.</label>
      <p>선택하면 기존 질문과 AI 답변을 받는 학부모도 볼 수 있습니다. 실제 이관은 상대방 수락 후 완료됩니다.</p>
      <IdentityRecheck purpose="CHILD_TRANSFER" childId={child.id} onProof={setToken}/>
      <button disabled={send.isPending} onClick={close}>취소</button><button disabled={!token || send.isPending} onClick={() => void send.mutateAsync(undefined).then(() => { close(); setNotice('이관 요청을 보냈습니다. 상대방 수락 전에는 탈퇴·삭제되지 않습니다.') }).catch(showError)}>이관 요청</button><ErrorNotice error={send.error}/>
    </TransferDialog>}
    {canTransfer && accepting && <TransferDialog title="자녀 이관 수락">
      <p>{accepting.senderName ?? '학부모'}님의 자녀 {accepting.childName ?? ''}을 연결합니다.</p><p>프로필·학습 기록·리포트 포함 · 기존 분석 상담 대화 {accepting.includeConversations ? '포함' : '미포함'}</p>
      <QueryFeedback query={documents}/>{documents.data && <ConsentFields documents={documents.data.items.filter(d => d.kind === 'GUARDIAN')} value={consents} onChange={setConsents}/>}
      <IdentityRecheck purpose="TRANSFER_ACCEPT" onProof={setToken}/>
      <button disabled={accept.isPending} onClick={close}>닫기</button><button disabled={!token || accept.isPending || !documents.data || !documents.data.items.filter(d => d.kind === 'GUARDIAN' && d.required).every(d => consents.some(c => c.documentId === d.documentId && c.version === d.version && c.agreed))} onClick={() => void accept.mutateAsync(undefined).then(async () => { close(); setNotice('이관을 완료했습니다.'); await refreshIdentity() }).catch(showError)}>동의하고 수락</button><ErrorNotice error={accept.error}/>
    </TransferDialog>}
    {limitOpen && <TransferDialog title="자녀 등록 한도"><p>해당 학부모는 자녀 등록 한도(3명)에 도달하여 이관받을 수 없습니다.</p><button onClick={() => setLimitOpen(false)}>확인</button></TransferDialog>}
  </div></Workspace>
}
