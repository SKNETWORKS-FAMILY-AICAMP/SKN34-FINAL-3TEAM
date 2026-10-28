import { useState } from 'react'
import { useNavigate } from 'react-router'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { restoreSession } from '../../data/classroom/useClassroom.ts'
import { useSession } from '../auth/sessionContext.ts'
import { ConsentFields } from './AccountForms.tsx'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import type { Child } from '../../domain/classroom.ts'
import type { Consent } from '../../domain/parent.ts'

export function ConsentSettings({ child }: { child?: Child }) {
  const history = useParentQuery(['consent-history'], (signal) => parentApi.consentHistory(signal))
  const documents = useParentQuery(['consents'], (signal) => parentApi.documents(signal))
  const save = useParentMutation(parentApi.saveConsents), withdraw = useParentMutation(parentApi.withdrawConsent)
  const [choices, setChoices] = useState<Consent[]>([]), [notice, setNotice] = useState('')
  const [refreshError, setRefreshError] = useState<unknown>(null)
  const { setSession } = useSession(), navigate = useNavigate()
  async function refreshState() {
    setRefreshError(null)
    try {
    const next = await restoreSession(true)
    setSession(next)
    setNotice('동의 상태를 저장했습니다. 삭제·탈퇴는 별도 요청이 필요합니다.')
    if (next.nextAction !== 'READY') navigate(next.startPath ?? '/parent/onboarding', { replace: true })
    } catch (error) { setRefreshError(error) }
  }
  return <section className="ws-card">
    <h2>동의 이력·철회</h2>
    <p>필수 동의 철회 시 계정 또는 해당 자녀의 이용이 제한됩니다. 삭제·탈퇴는 별도 요청이며 이 화면에서 실행하지 않습니다.</p>
    <QueryFeedback query={history} />
    {history.data?.items.map((entry) => <article key={entry.consentId}>
      <p>{entry.document.title} · v{entry.document.version} · {entry.studentId ? `자녀 ${entry.studentId === child?.id ? child.nickname : entry.studentId}` : '계정'} · {entry.status === 'WITHDRAWN' ? '철회/거부' : '동의'}</p>
      <p>기록 시점 {entry.agreedAt}{entry.withdrawnAt && ` · 철회 ${entry.withdrawnAt}`}</p>
      {entry.agreed && entry.status === 'AGREED' && <button className="cj-secondary" disabled={withdraw.isPending} onClick={() => {
        void withdraw.mutateAsync(entry.consentId).then(refreshState).catch(() => {})
      }}>{entry.document.title} 철회</button>}
    </article>)}
    {child?.guardianConsentRequired && <form className="ws-form" onSubmit={(e) => {
      e.preventDefault()
      void save.mutateAsync({ childId: child.id, consents: choices }).then(refreshState).catch(() => {})
    }}>
      <h3>{child.nickname} 법정대리인 재동의</h3>
      <QueryFeedback query={documents} />
      {documents.data && !documents.error && <ConsentFields documents={documents.data.items.filter((d) => d.kind === 'GUARDIAN')} value={choices} onChange={setChoices} />}
      <button disabled={!documents.data || !!documents.error || save.isPending}>법정대리인 동의 저장</button>
    </form>}
    <ErrorNotice error={withdraw.error ?? save.error ?? refreshError} />
    {refreshError != null && <button onClick={() => { void refreshState() }}>저장 후 상태 다시 확인</button>}
    {notice && <p role="status">{notice}</p>}
  </section>
}
