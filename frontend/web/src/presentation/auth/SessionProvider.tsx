import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router'
import type { Session, DemoScenario } from '../../domain/classroom.ts'
import { restoreSession } from '../../data/classroom/useClassroom.ts'
import { queryClient } from '../../data/queryClient.ts'
import { ApiError, watchAuthChange, waitForPendingRefresh, hasAccessToken } from '../../data/apiClient.ts'
import { AuthContext } from './sessionContext.ts'

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  const [loginPath, setLoginPath] = useState<'/login' | '/student/login'>('/login')
  const [selected, setSelected] = useState('')
  const [restoreError, setRestoreError] = useState('')
  const [expired, setExpired] = useState(false)
  const [scenario, setScenario] = useState<DemoScenario>('normal')
  const navigate = useNavigate()

  useEffect(() => {
    let revision = 0
    let active = true
    const clear = () => { setSession(null); setSelected(''); queryClient.clear(); setRestoreError('') }
    const studentEntry = () => {
      setLoginPath('/student/login')
      revision++
      clear()
      setReady(true)
      setExpired(false)
      const from = window.location.pathname
      navigate('/student/login', {
        replace: true,
        state: from.startsWith('/student/') && from !== '/student/login' ? { from } : undefined,
      })
    }
    const expire = () => { setLoginPath('/login'); revision++; clear(); setReady(true); setExpired(true) }
    const restore = async (fresh: boolean) => {
      if (!fresh && window.location.pathname.startsWith('/student/') && !hasAccessToken()) { studentEntry(); return }
      const current = ++revision
      setReady(false)
      try {
        if (fresh) await waitForPendingRefresh()
        const next = await restoreSession(fresh)
        if (active && current === revision) { setSession(next); setLoginPath(next.role === 'STUDENT' ? '/student/login' : '/login'); setExpired(false) }
      } catch (error) {
        if (!active || current !== revision) return
        if (error instanceof ApiError && error.problem.status === 401) {
          clear()
          if (window.location.pathname.startsWith('/student/')) navigate('/student/login', { replace: true })
        } else setRestoreError('로그인 상태를 확인하지 못했습니다. 잠시 후 새로고침해 주세요.')
      } finally { if (active && current === revision) setReady(true) }
    }
    const changed = () => { setLoginPath('/login'); clear(); void restore(true) }
    const stop = watchAuthChange((mode) => {
      if (mode === 'STUDENT') studentEntry()
      else if (mode === 'LOGOUT') {
        setLoginPath('/login'); revision++; clear(); setReady(true); setExpired(false); navigate('/login', { replace: true })
      } else changed()
    })
    window.addEventListener('sagomungchi:session-expired', expire)
    window.addEventListener('sagomungchi:student-auth-required', studentEntry)
    window.addEventListener('sagomungchi:session-changed', changed)
    void restore(false)
    return () => {
      active = false
      stop()
      window.removeEventListener('sagomungchi:session-expired', expire)
      window.removeEventListener('sagomungchi:student-auth-required', studentEntry)
      window.removeEventListener('sagomungchi:session-changed', changed)
    }
  }, [navigate])
  return <AuthContext.Provider value={{ session, setSession, ready, loginPath, selected, setSelected, expired, setExpired, scenario, setScenario }}>
    {restoreError ? <main><p role="alert">{restoreError}</p><button onClick={() => window.location.reload()}>새로고침</button></main> : children}
  </AuthContext.Provider>
}
