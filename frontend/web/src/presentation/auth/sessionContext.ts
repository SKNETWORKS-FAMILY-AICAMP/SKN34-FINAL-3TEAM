import { createContext, useContext } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { Session, DemoScenario } from '../../domain/classroom.ts'
export interface AuthState {
  session: Session | null
  setSession: Dispatch<SetStateAction<Session | null>>
  ready: boolean
  loginPath: '/login' | '/student/login'
  selected: string
  setSelected: Dispatch<SetStateAction<string>>
  expired: boolean
  setExpired: Dispatch<SetStateAction<boolean>>
  scenario:DemoScenario
  setScenario:Dispatch<SetStateAction<DemoScenario>>
}
export const AuthContext = createContext<AuthState | null>(null)
export function useSession() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('SessionProvider가 필요합니다.')
  return context
}
