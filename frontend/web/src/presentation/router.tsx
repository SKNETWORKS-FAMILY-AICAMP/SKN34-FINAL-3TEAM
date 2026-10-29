import { createBrowserRouter, Navigate, Outlet } from 'react-router'
import { ClassroomApp } from './ClassroomApp.tsx'
import { SessionProvider } from './auth/SessionProvider.tsx'
import { LoginGate, RoleLayout } from './common/RoleLayout.tsx'
import { SignupPage } from './parent/AccountForms.tsx'
import { ParentWorkspace } from './parent/ParentWorkspace.tsx'
import { AdminWorkspace } from './admin/AdminWorkspace.tsx'
import { OAuthCompletePage } from './auth/OAuthCompletePage.tsx'
import { AuthOnboarding } from './auth/AuthOnboarding.tsx'
import { SupportResults } from './support/SupportResults.tsx'
import { DeviceLogin } from './student/DeviceLogin.tsx'

// URL 입력만으로 역할을 부여하지 않는다. 로그인 응답/학생 세션으로 진입한다.
export const router = createBrowserRouter([
  {
    element: (
      <SessionProvider>
        <Outlet />
      </SessionProvider>
    ),
    children: [
      { path: '/oauth/complete', element: <OAuthCompletePage /> },
      // 자녀 기기 진입(P01 개정, #59): 등록 기기 + PIN. 학생 토큰 만료·새로고침 때도 여기로 온다.
      { path: '/student/login', element: <LoginGate />, children: [{ index: true, element: <DeviceLogin /> }] },
      {
        path: '/signup',
        element: <LoginGate />,
        children: [{ index: true, element: <SignupPage /> }],
      },
      {
        path: '/login',
        element: <LoginGate />,
        children: [{ index: true, element: <ClassroomApp /> }],
      },
      ...(['STUDENT', 'PARENT', 'ADMIN'] as const).map((role) => ({
        path: `/${role.toLowerCase()}`,
        element: <RoleLayout role={role} />,
        children: [
          ...(role !== 'ADMIN' ? [{ path: 'support', element: <SupportResults /> }] : []),
          ...(role === 'PARENT' ? [
            { path: 'onboarding', element: <AuthOnboarding /> },
            { path: 'children/new', element: <AuthOnboarding /> },
          ] : []),
          {
            index: true,
            element: (
              <Navigate
                to={role === 'STUDENT' ? 'home' : role === 'PARENT' ? 'journal' : 'home'}
                replace
              />
            ),
          },
          {
            path: '*',
            element:
              role === 'PARENT' ? (
                <ParentWorkspace />
              ) : role === 'ADMIN' ? (
                <AdminWorkspace />
              ) : (
                <ClassroomApp />
              ),
          },
        ],
      })),
      { path: '*', element: <Navigate to="/login" replace /> },
    ],
  },
])
