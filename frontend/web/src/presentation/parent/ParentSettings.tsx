import { UserRound, ShieldCheck, Settings2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import type { Child } from '../../domain/classroom.ts'
import { ProfileSettings } from './AccountForms.tsx'
import { ConsentSettings } from './ConsentSettings.tsx'
import { AccountLifecycle } from '../service/AccountLifecycle.tsx'
import { Withdrawal } from '../service/Withdrawal.tsx'
import { useState } from 'react'
import { ChildRegistration } from './AccountForms.tsx'
import { Modal } from '../shared/ClassroomParts.tsx'
import { useSession } from '../auth/sessionContext.ts'

const settingsTabs = [['profile', '프로필'], ['sharing', '공개·동의'], ['account', '계정 관리']] as const

export function ParentSettings({ child, childCount, onCreated }: { child?: Child; childCount?: number; onCreated: (child: Child) => void }) {
  const [registration, setRegistration] = useState(false)
  const [params, setParams] = useSearchParams()
  const selected = params.get('section') ?? 'profile'
  const tab = ['profile', 'sharing', 'account'].includes(selected) ? selected : 'profile'
  function selectTab(id: string) {
    const next = new URLSearchParams(params); next.set('section', id); setParams(next)
  }
  return <section className="parent-settings">
    <header className="parent-page-head"><h1>계정·자녀 설정</h1><p>프로필, 공개·동의, 계정 관리를 나눠 확인할 수 있습니다.</p></header>
    <div className="parent-setting-context"><span className="settings-avatar" aria-hidden="true"><UserRound size={26} strokeWidth={1.6}/></span><strong>{child ? `${child.nickname}의 설정` : '보호자 계정 설정'}</strong><span>{childCount === undefined ? '자녀 확인 중' : `자녀 ${childCount}/3명 등록`}</span></div>
    <div className="settings-workspace"><nav className="parent-tabs" role="tablist" aria-label="설정 항목">
      {settingsTabs.map(([id, label], index) => <button key={id} role="tab" id={`settings-${id}`} tabIndex={tab === id ? 0 : -1} aria-selected={tab === id} aria-controls={`settings-panel-${id}`} onClick={() => selectTab(id)} onKeyDown={event => {
        const next = event.key === 'ArrowRight' ? (index + 1) % settingsTabs.length : event.key === 'ArrowLeft' ? (index + settingsTabs.length - 1) % settingsTabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? settingsTabs.length - 1 : null
        if (next === null) return
        event.preventDefault()
        const nextId = settingsTabs[next][0]
        selectTab(nextId); document.getElementById(`settings-${nextId}`)?.focus()
      }}>{index === 0 ? <UserRound size={18} aria-hidden="true"/> : index === 1 ? <ShieldCheck size={18} aria-hidden="true"/> : <Settings2 size={18} aria-hidden="true"/>}{label}</button>)}
    </nav>
    <div role="tabpanel" id={`settings-panel-${tab}`} aria-labelledby={`settings-${tab}`} className="parent-settings-panel">
      {tab === 'profile' ? <><ProfileSettings child={child} /><section className="ws-card parent-add-child">
        <div><h2>자녀 추가 등록</h2><p>{childCount === undefined ? '연결된 자녀를 확인하고 있습니다.' : `자녀는 최대 3명까지 등록할 수 있습니다. 현재 ${childCount}명 등록`}</p></div>
        <button className="cj-primary" disabled={childCount === undefined || childCount >= 3} onClick={() => setRegistration(true)}>자녀 추가 등록</button>
      </section></>
        : tab === 'sharing' ? <ConsentSettings child={child} />
        : <><LoginIdCard /><p>연결 해제와 삭제·탈퇴는 다른 작업입니다. 대상과 영향을 확인한 뒤 본인 확인을 진행합니다.</p><Link to="/parent/transfers">자녀 이관 · 받은 요청 확인</Link>{child && <AccountLifecycle key={child.id} child={child} />}<Withdrawal /></>}
    </div>
    </div>
    {registration && <Modal title="자녀 프로필 등록" onClose={() => setRegistration(false)}><ChildRegistration onCreated={value => { setRegistration(false); onCreated(value) }} /></Modal>}
  </section>
}

/** #683: 로그인 아이디(Google 계정은 Google 이메일). 서버가 주지 않으면 표시하지 않는다 */
function LoginIdCard() {
  const session = useSession().session
  if (!session?.loginId) return null
  return <section className="ws-card parent-login-id" aria-labelledby="login-id-title">
    <h2 id="login-id-title">로그인 아이디</h2>
    <p><strong>{session.loginId}</strong></p>
    <small>{session.authMethod === 'GOOGLE' ? 'Google 계정으로 로그인합니다. 아이디는 Google 이메일입니다.' : '아이디와 비밀번호로 로그인합니다.'}</small>
  </section>
}
