import { Navigate, useLocation } from 'react-router'

/** 기존 계정 주소는 하나의 설정 화면으로 연결한다 (#427). */
export function AccountPage() {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  params.set('section', 'account')
  return <Navigate to={'/parent/settings?' + params.toString()} replace />
}
