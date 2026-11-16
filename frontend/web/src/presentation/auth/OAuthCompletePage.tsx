import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { restoreSession } from '../../data/classroom/useClassroom.ts'
import { ApiError, notifyAuthChange } from '../../data/apiClient.ts'
import { useSession } from './sessionContext.ts'
import { roleStart } from '../../domain/navigation.ts'

export function OAuthCompletePage() {
  const { ready, session, setSession } = useSession()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!ready) return
    let active = true
    // 시작 시 이미 확인한 세션은 그대로 사용한다. Google 코드는 다시 교환하지 않는다.
    void (session ? Promise.resolve(session) : restoreSession(true)).then((next) => {
      if (!active) return
      setSession(next)
      notifyAuthChange(next.role)
      navigate(next.startPath ?? roleStart(next.role), { replace: true })
    }).catch((reason) => { if (active) setError(reason instanceof ApiError && reason.problem.status >= 500
      ? '잠시 로그인 상태를 확인하지 못했습니다. 다시 확인해 주세요.'
      : '로그인을 확인하지 못했습니다. Google 로그인을 다시 진행해 주세요.') })
    return () => { active = false }
  }, [ready, session, setSession, navigate, retry])
  return <main className="ws-card"><h1>Google 로그인 확인</h1>
    {error ? <><p role="alert">{error}</p><button className="cj-secondary" onClick={() => { setError(''); setRetry(value => value + 1) }}>로그인 상태 다시 확인</button><a href="/login">로그인으로 돌아가기</a></> : <p role="status">로그인 상태를 확인하고 있습니다.</p>}
  </main>
}
