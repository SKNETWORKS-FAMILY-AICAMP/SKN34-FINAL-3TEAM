import { useSession } from './sessionContext.ts'
import { useAuthentication } from '../../data/classroom/useClassroom.ts'
import { useNavigate } from 'react-router'

/** Consent writes/registration are #37; never fabricate completion while those APIs are absent. */
export function AuthOnboarding() {
  const { session, setSession } = useSession()
  const auth = useAuthentication()
  const navigate = useNavigate()
  const consent = session?.nextAction === 'CONSENT_REQUIRED'
  return <main className="ws-card">
    <h1>{consent ? '이용 안내·필수 동의' : '자녀 등록'}</h1>
    <p>{consent ? 'Google 로그인을 완료했습니다. 이용을 시작하려면 필수 동의를 완료해야 합니다.' : '학습을 시작하려면 자녀를 등록해야 합니다.'}</p>
    <p role="status">{consent ? '이용 동의 화면을 준비하고 있습니다.' : '자녀 등록 화면을 준비하고 있습니다.'}</p>
    <button className="cj-secondary" onClick={() => {
      void auth.logout.mutateAsync().then(() => { setSession(null); navigate('/login', { replace: true }) }).catch(() => {})
    }}>로그아웃</button>
    {auth.logout.error && <p role="alert">로그아웃하지 못했습니다. 다시 시도해 주세요.</p>}
  </main>
}
