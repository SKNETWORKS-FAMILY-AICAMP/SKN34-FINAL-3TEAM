import { Suspense } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'
import type { Role } from '../../domain/classroom.ts'
import { useSession } from '../auth/sessionContext.ts'
import { roleStart } from '../../domain/navigation.ts'
import { parentLoginRequired } from '../../data/apiClient.ts'
import { useNotificationStream } from '../../data/notifications.ts'

export function RoleLayout({ role }: { role: Role }) {
  const { session, ready, loginPath } = useSession(),
    location = useLocation()
  // 동의·자녀 등록 전 학부모는 연결하지 않는다(동의 필요 응답이 온보딩 이동을 다시 일으키지 않도록).
  useNotificationStream(ready && session?.role === role && role !== 'STUDENT' && (session.nextAction ?? 'READY') === 'READY' ? role : null)
  if (!ready) return <p role="status">로그인 상태를 확인하고 있습니다.</p>
  if (!session) return <Navigate to={parentLoginRequired() ? '/login' : role === 'STUDENT' ? '/student/login' : loginPath} replace state={{ from: location.pathname + location.search }} />
  const transferInbox = import.meta.env.VITE_GUARDIAN_TRANSFER_ENABLED === 'true' && session.nextAction === 'CHILD_REGISTRATION_REQUIRED' && location.pathname === '/parent/transfers'
  if (session.role === 'PARENT' && session.nextAction && session.nextAction !== 'READY' && !transferInbox && location.pathname !== session.startPath && !['/parent/account','/parent/help','/parent/support','/parent/billing'].includes(location.pathname))
    return <Navigate to={session.startPath ?? '/parent/onboarding'} replace />
  if (session.role !== role) return <Navigate to={roleStart(session.role)} replace />
  return (
    <section
      data-role-layout={role.toLowerCase()}
      aria-label={
        role === 'STUDENT'
          ? '학생 학습 공간'
          : role === 'PARENT'
            ? '학부모 기록 공간'
            : '관리자 운영 공간'
      }
    >
      <Suspense fallback={<PageLoading />}>
        <Outlet />
      </Suspense>
    </section>
  )
}
/** 지연 로딩하는 화면 코드를 받는 동안 표시한다. */
export function PageLoading() {
  return <p role="status">화면을 불러오고 있습니다.</p>
}
export function LoginGate() {
  const { session, ready, loginPath } = useSession()
  const location = useLocation()
  if (!ready) return <p role="status">로그인 상태를 확인하고 있습니다.</p>
  // Explicit guardian entry wins over the previous student route while state updates settle.
  if (!session && location.pathname === '/login' && parentLoginRequired()) return <Outlet />
  if (!session && loginPath === '/student/login' && location.pathname !== loginPath) return <Navigate to={loginPath} replace />
  return session ? <Navigate to={session.startPath ?? roleStart(session.role)} replace /> : <Outlet />
}
