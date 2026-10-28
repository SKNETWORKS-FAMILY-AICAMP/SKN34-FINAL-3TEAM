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
      const { pathname, search } = window.location
      // QR로 연 /student/login?code=…는 그대로 둔다. 초기 인증 확인에서 코드를 지우면 등록할 수 없다.
      if (pathname !== '/student/login') navigate('/student/login', {
        replace: true,
        state: pathname.startsWith('/student/') && pathname !== '/student/login' ? { from: pathname + search } : undefined,
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
          if (window.location.pathname.startsWith('/student/') && window.location.pathname !== '/student/login')
            navigate('/student/login', { replace: true })
        } else {
          // core-service가 꺼져 있으면 Vite 프록시가 502를 준다. 로그인 상태 실패와 구분해 원인을 알린다.
          const down = error instanceof TypeError || (error instanceof ApiError && [502, 503, 504].includes(error.problem.status))
          setRestoreError(down ? 'SERVER_DOWN' : '로그인 상태를 확인하지 못했습니다. 잠시 후 새로고침해 주세요.')
        }
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
    {restoreError ? (
      <main style={{ maxWidth: 560, margin: '15vh auto', padding: '0 20px', fontFamily: 'system-ui, sans-serif', lineHeight: 1.6 }}>
        {restoreError === 'SERVER_DOWN' ? (
          <>
            <p role="alert"><strong>서버(core-service)에 연결하지 못했습니다.</strong> 로그인 상태를 확인할 수 없어 화면을 열지 않았습니다.</p>
            {import.meta.env.DEV && (
              <p>
                로컬 개발: 저장소 루트에서 <code>docker compose up --build</code>로 백엔드를 띄운 뒤 새로고침하거나,
                백엔드 없이 화면만 보려면 <code>VITE_API_MOCK=true</code>로 <code>npm run dev</code>를 실행해 주세요.
              </p>
            )}
          </>
        ) : (
          <p role="alert">{restoreError}</p>
        )}
        <button onClick={() => window.location.reload()}>새로고침</button>
      </main>
    ) : children}
  </AuthContext.Provider>
}
