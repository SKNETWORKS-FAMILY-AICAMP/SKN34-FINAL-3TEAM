import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session, DemoScenario } from '../../domain/classroom.ts'
import { restoreSession } from '../../data/classroom/useClassroom.ts'

import { AuthContext } from './sessionContext.ts'
export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null),
    [ready, setReady] = useState(false),
    [selected, setSelected] = useState('')
  const [expired, setExpired] = useState(false)
  const [scenario,setScenario]=useState<DemoScenario>('normal')
  useEffect(() => {
    const expire = () => setExpired(true)
    window.addEventListener('sagomungchi:session-expired', expire)
    return () => window.removeEventListener('sagomungchi:session-expired', expire)
  }, [])
  useEffect(() => {
    let active = true
    void restoreSession()
      .then((session) => {
        if (active) setSession(session)
      })
      .catch(() => {
        /* 최초 미로그인은 정상이며 보호 화면은 표시하지 않습니다. */
      })
      .finally(() => {
        if (active) setReady(true)
      })
    return () => {
      active = false
    }
  }, [])
  return (
    <AuthContext.Provider
      value={{ session, setSession, ready, selected, setSelected, expired, setExpired,scenario,setScenario }}
    >
      {children}
    </AuthContext.Provider>
  )
}
