import { useState } from 'react'
import { useSession } from './sessionContext.ts'
import { restoreSession, useAuthentication } from '../../data/classroom/useClassroom.ts'
import { useNavigate } from 'react-router'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { ChildRegistration, ConsentFields } from '../parent/AccountForms.tsx'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import type { Consent } from '../../domain/parent.ts'

export function AuthOnboarding() {
  const { session, setSession } = useSession()
  const auth = useAuthentication(), navigate = useNavigate()
  const documents = useParentQuery(['consents'], (signal) => parentApi.documents(signal))
  const [consents, setConsents] = useState<Consent[]>([])
  const [completionError, setCompletionError] = useState<unknown>(null)
  const save = useParentMutation(parentApi.saveConsents)
  const consent = session?.nextAction === 'CONSENT_REQUIRED'
  async function proceed() {
    try {
      const next = await restoreSession(true)
      setSession(next)
      navigate(next.startPath ?? '/parent/journal', { replace: true })
    } catch (error) { setCompletionError(error) }
  }
  return <main className="ws-card">
    <h1>{consent ? '이용 안내·필수 동의' : '자녀 등록'}</h1>
    {consent ? <>
      <p>현재 문서를 확인하고 동의해 주세요. 필수 동의를 철회하면 계정 이용이 제한되며 삭제·탈퇴는 별도 요청이 필요합니다.</p>
      <QueryFeedback query={documents} />
      <form className="ws-form" onSubmit={(e) => {
        e.preventDefault()
        const choices = documents.data?.items.filter((d) => d.kind !== 'GUARDIAN').map((d) => ({
          documentId: d.documentId, version: d.version,
          agreed: consents.some((c) => c.documentId === d.documentId && c.version === d.version && c.agreed),
        })) ?? []
        void save.mutateAsync({ consents: choices }).then(proceed).catch(() => {})
      }}>
        {documents.data && !documents.error && <ConsentFields documents={documents.data.items.filter((d) => d.kind !== 'GUARDIAN')} value={consents} onChange={setConsents} />}
        <button className="cj-primary" disabled={!documents.data?.items.length || !!documents.error || save.isPending}>동의 저장하고 계속하기</button>
        <ErrorNotice error={save.error} />
      </form>
    </> : <ChildRegistration onCreated={() => { void proceed() }} />}
    {completionError != null && <><ErrorNotice error={completionError} /><button onClick={() => { void proceed() }}>저장 후 상태 다시 확인</button></>}
    <button className="cj-secondary" onClick={() => {
      void auth.logout.mutateAsync().then(() => { setSession(null); navigate('/login', { replace: true }) }).catch(() => {})
    }}>로그아웃</button>
    {auth.logout.error && <p role="alert">로그아웃하지 못했습니다. 다시 시도해 주세요.</p>}
  </main>
}
