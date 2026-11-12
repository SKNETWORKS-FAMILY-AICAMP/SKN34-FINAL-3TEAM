import { createBrowserRouter, Navigate, Outlet } from 'react-router'
import { SessionProvider } from './auth/SessionProvider.tsx'
import { LoginGate, PageLoading, RoleLayout } from './common/RoleLayout.tsx'
import { OAuthCompletePage } from './auth/OAuthCompletePage.tsx'
import { SupportEntry } from './support/SupportEntry.tsx'
import { SupportResults } from './support/SupportResults.tsx'
import { DeviceLogin } from './student/DeviceLogin.tsx'
import { ServiceCenter } from './service/ServiceCenter.tsx'
import { WithdrawalReceipt } from './service/Withdrawal.tsx'
import { LoginHelp } from './service/LoginHelp.tsx'
import { lazy, Suspense } from 'react'
import type { ComponentType } from 'react'

// 역할별 작업 공간과 결제·계정 화면은 들어갈 때 받는다(#247). 학생 기기 첫 화면은 학부모·관리자 코드를 받지 않는다.
const page = <P extends object>(load: () => Promise<ComponentType<P>>) => lazy(async () => ({ default: await load() }))
const ClassroomApp = page(() => import('./ClassroomApp.tsx').then(m => m.ClassroomApp))
const ParentWorkspace = page(() => import('./parent/ParentWorkspace.tsx').then(m => m.ParentWorkspace))
const AdminWorkspace = page(() => import('./admin/AdminWorkspace.tsx').then(m => m.AdminWorkspace))
const AdminLoginPage = page(() => import('./admin/AdminLoginPage.tsx').then(m => m.AdminLoginPage))
const SignupPage = page(() => import('./parent/AccountForms.tsx').then(m => m.SignupPage))
const PaymentResult = page(() => import('./parent/ParentPayments.tsx').then(m => m.PaymentResult))
const BillingResult = page(() => import('./parent/BillingResult.tsx').then(m => m.BillingResult))
const AccountPage = page(() => import('./service/AccountPage.tsx').then(m => m.AccountPage))
const GuardianTransfers = page(() => import('./service/GuardianTransfers.tsx').then(m => m.GuardianTransfers))
const AuthOnboarding = page(() => import('./auth/AuthOnboarding.tsx').then(m => m.AuthOnboarding))
const ReviewPage = import.meta.env.DEV && import.meta.env.VITE_API_MOCK === 'true' ? lazy(() => import('./service/ReviewPage.tsx').then(m => ({ default: m.ReviewPage }))) : null

// URL 입력만으로 역할을 부여하지 않는다. 로그인 응답/학생 세션으로 진입한다.
export const router = createBrowserRouter([
  {
    element: (
      <SessionProvider>
        <Suspense fallback={<PageLoading />}>
          <Outlet />
        </Suspense>
      </SessionProvider>
    ),
    children: [
      { path: '/payment/billing/success', element: <BillingResult /> },
      { path: '/payment/billing/fail', element: <BillingResult failed /> },
      { path: '/payment/success', element: <PaymentResult /> },
      { path: '/payment/fail', element: <PaymentResult failed /> },
      { path: '/admin/login', element: <LoginGate />, children: [{ index: true, element: <AdminLoginPage /> }] },
      { path: '/login-help', element: <LoginHelp /> },
      ...(ReviewPage ? [{ path: '/review', element: <Suspense fallback={<p>점검표를 불러오고 있습니다.</p>}><ReviewPage /></Suspense> }] : []),
      { path: '/withdrawal-status', element: <WithdrawalReceipt /> },
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
          ...(['help', 'notices', 'notifications'] as const).map(page => ({ path: page, element: role === 'PARENT' ? <ParentWorkspace /> : <ServiceCenter page={page} /> })),
          ...(role === 'ADMIN' ? [] : [{ path: 'support', element: role === 'PARENT' ? <ParentWorkspace /> : <SupportEntry /> }]),
          ...(role !== 'ADMIN' ? [{ path: 'support/results', element: role === 'PARENT' ? <ParentWorkspace /> : <SupportResults /> }] : []),
          ...(role === 'PARENT' ? [
            { path: 'account', element: <AccountPage /> },
            { path: 'transfers', element: <GuardianTransfers /> },
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
