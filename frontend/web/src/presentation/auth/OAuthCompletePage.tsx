import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { restoreSession } from '../../data/classroom/useClassroom.ts'
import { notifyAuthChange } from '../../data/apiClient.ts'
import { useSession } from './sessionContext.ts'
import { roleStart } from '../../domain/navigation.ts'

export function OAuthCompletePage() {
  const { ready, setSession } = useSession()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  useEffect(() => {
    if (!ready) return
    let active = true
    void restoreSession().then((next) => {
      if (!active) return
      setSession(next)
      notifyAuthChange(next.role)
      navigate(next.startPath ?? roleStart(next.role), { replace: true })
    }).catch(() => { if (active) setError('로그인을 확인하지 못했습니다. 다시 로그인해 주세요.') })
    return () => { active = false }
  }, [ready, setSession, navigate])
  return <main className="ws-card"><h1>Google 로그인 확인</h1>
    {error ? <><p role="alert">{error}</p><a href="/login">로그인으로 돌아가기</a></> : <p role="status">로그인 상태를 확인하고 있습니다.</p>}
  </main>
}
