import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { restoreSession } from '../../data/classroom/useClassroom.ts'
import { useSession } from '../auth/sessionContext.ts'
import { ConsentFields } from './AccountForms.tsx'
import { COMMUNITY_CONSENT_ANCHOR } from './consentLinks.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { formatKoreanDateTime } from '../common/dateTime.ts'
import { FileText, ChevronRight } from 'lucide-react'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import type { Child } from '../../domain/classroom.ts'
import type { Consent } from '../../domain/parent.ts'

export function ConsentSettings({ child }: { child?: Child }) {
  const history = useParentQuery(['consent-history'], (signal) => parentApi.consentHistory(signal))
  const documents = useParentQuery(['consents'], (signal) => parentApi.documents(signal))
  const save = useParentMutation(parentApi.saveConsents), withdraw = useParentMutation(parentApi.withdrawConsent)
  const [choices, setChoices] = useState<Consent[]>([]), [notice, setNotice] = useState('')
  const [reading, setReading] = useState<{ title: string; version: string; content?: string; agreedAt?: string; withdrawnAt?: string } | null>(null)
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
  return <section className="ws-card parent-consent-settings">
    <h2>동의 이력·철회</h2>
    <p>필수 동의 철회 시 계정 또는 해당 자녀의 이용이 제한됩니다. 삭제·탈퇴는 별도 요청이며 이 화면에서 실행하지 않습니다.</p>
    <QueryFeedback query={history} />
    {history.data?.items.filter(entry => !entry.studentId || entry.studentId === child?.id).map((entry) => <article className="parent-consent-entry" key={entry.consentId}>
      <header><h3>{entry.document.title}</h3><span className="consent-state">{entry.status === 'WITHDRAWN' ? '철회함' : entry.status === 'AGREED' && entry.agreed ? '동의함' : '상태 확인 필요'}</span></header>
      <p>적용 대상 · {entry.studentId ? child?.nickname ?? '선택한 자녀' : '보호자 계정'}</p>
      <button type="button" className="consent-document-trigger" aria-haspopup="dialog" onClick={() => setReading({title: entry.document.title, version: entry.document.version, content: entry.document.content, agreedAt: entry.agreedAt, withdrawnAt: entry.withdrawnAt ?? undefined})}><FileText size={18} aria-hidden="true"/><span>동의 문서·이력 보기</span><ChevronRight size={18} aria-hidden="true"/></button>
      {entry.agreed && entry.status === 'AGREED' && <footer className="consent-entry-actions"><button className="cj-secondary" disabled={withdraw.isPending || !!history.error || history.isPending} onClick={() => {
        void withdraw.mutateAsync(entry.consentId).then(refreshState).catch(() => {})
      }}>{entry.document.title} 철회</button></footer>}
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
    {child && <CommunityConsent child={child} />}
    {reading && <Modal title={reading.title} onClose={() => setReading(null)}><div className="consent-document-reader"><dl><div><dt>문서 버전</dt><dd>{reading.version}</dd></div>{reading.agreedAt && <div><dt>동의 일시</dt><dd>{formatKoreanDateTime(reading.agreedAt)}</dd></div>}{reading.withdrawnAt && <div><dt>철회 일시</dt><dd>{formatKoreanDateTime(reading.withdrawnAt)}</dd></div>}</dl><h3>동의 문서</h3>{reading.content?.trim() ? <div className="consent-document-text">{reading.content}</div> : <p role="note">이 버전의 동의 문서 본문을 불러오지 못했습니다. 문의를 통해 확인해 주세요.</p>}</div></Modal>}
  </section>
}

/**
 * 풀이 공유 커뮤니티 선택 동의 (P20, API 명세 2.9). 자녀 단위이고 기본은 미동의.
 * 동의해도 공개는 자녀가 직접 켜야 하고, 철회하면 자녀의 공유물이 바로 비공개가 된다.
 */
function CommunityConsent({ child }: { child: Child }) {
  const history = useParentQuery(['consent-history'], (signal) => parentApi.consentHistory(signal))
  const documents = useParentQuery(['consents'], (signal) => parentApi.documents(signal))
  const save = useParentMutation(parentApi.saveConsents), withdraw = useParentMutation(parentApi.withdrawConsent)
  const doc = documents.data?.items.find((d) => d.kind === 'COMMUNITY')
  const current = history.data?.items.find((e) => e.document.kind === 'COMMUNITY' && e.studentId === child.id && e.document.documentId === doc?.documentId && e.document.version === doc?.version)
  const agreed = !!current && current.agreed && current.status === 'AGREED'
  const blocked = !!child.guardianConsentRequired
  const ref = useRef<HTMLElement>(null), { hash } = useLocation()
  // 대시보드의 "커뮤니티 동의하기"(#433)로 들어오면 이 영역을 바로 보여 준다.
  useEffect(() => { if (hash === `#${COMMUNITY_CONSENT_ANCHOR}`) ref.current?.scrollIntoView?.({ block: 'start' }) }, [hash])
  return <section id={COMMUNITY_CONSENT_ANCHOR} ref={ref} className="community-consent-panel" aria-labelledby="community-consent-h">
    <QueryFeedback query={history} />
    <header className="community-consent-heading"><div><h3 id="community-consent-h">풀이 공유 커뮤니티</h3><p>{child.nickname}의 커뮤니티 이용 설정</p></div><span className="consent-optional">선택 동의</span></header>
    {blocked && <p role="note">법정대리인 동의를 먼저 마쳐 주세요. 위의 법정대리인 재동의를 저장하면 커뮤니티 동의를 할 수 있습니다.</p>}
    {!blocked && <QueryFeedback query={documents} />}
    {!blocked && documents.data && !documents.error && !doc && <p role="note">커뮤니티 동의 문서를 아직 받지 못했습니다. 잠시 뒤 다시 확인해 주세요.</p>}
    {!blocked && doc && <>
      <div className="community-consent-status" role="status"><span>현재 상태</span><strong>{history.isPending ? '확인 중' : history.error ? '확인할 수 없음' : agreed ? '동의함' : '동의하지 않음'}</strong></div>
      <dl className="community-consent-guide"><div><dt>공유 시작</dt><dd>보호자가 동의한 뒤, 자녀가 직접 공개 설정을 켜야 합니다.</dd></div><div><dt>동의 철회</dt><dd>자녀가 공유한 풀이가 바로 비공개로 바뀝니다.</dd></div></dl>
      <details className="community-consent-document"><summary>동의 문서 전문 보기 <span>v{doc.version}</span></summary><div className="parent-document-body">{doc.content}</div></details>
      <div className="community-consent-actions">
      {agreed ? (
        <button className="cj-secondary" disabled={withdraw.isPending || !!history.error || history.isPending} onClick={() => { void withdraw.mutateAsync(current!.consentId).catch(() => {}) }}>
          커뮤니티 동의 철회
        </button>
      ) : (
        <button className="cj-secondary" disabled={save.isPending || history.isPending || !!history.error} onClick={() => {
          void save.mutateAsync({ childId: child.id, consents: [{ documentId: doc.documentId, version: doc.version, agreed: true }] }).catch(() => {})
        }}>
          커뮤니티 이용에 동의
        </button>
      )}
      </div>
    </>}
    <ErrorNotice error={save.error ?? withdraw.error} />
  </section>
}
