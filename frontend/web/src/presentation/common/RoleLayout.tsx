import { Navigate, Outlet, useLocation } from 'react-router'
import type { Role } from '../../domain/classroom.ts'
import { useSession } from '../auth/sessionContext.ts'
import { roleStart } from '../../domain/navigation.ts'

export function RoleLayout({ role }: { role: Role }) {
  const { session, ready } = useSession(),
    location = useLocation()
  if (!ready) return <p role="status">로그인 상태를 확인하고 있습니다.</p>
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />
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
      <Outlet />
    </section>
  )
}
export function LoginGate() {
  const { session, ready } = useSession()
  if (!ready) return <p role="status">로그인 상태를 확인하고 있습니다.</p>
  return session ? <Navigate to={roleStart(session.role)} replace /> : <Outlet />
}
