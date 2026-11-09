import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { isDemo, useAuthentication } from '../../data/classroom/useClassroom.ts'
import { roleStart } from '../../domain/navigation.ts'
import { useSession } from '../auth/sessionContext.ts'
import { Brand, ErrorNotice } from '../shared/ClassroomParts.tsx'
import './admin-login.css'

/** 사용자 화면에서 링크하지 않는 관리자 전용 주소. 가입 없이 등록된 관리자 계정만 로그인한다 (#369). */
export function AdminLoginPage() {
  const auth = useAuthentication(), { setSession, setSelected } = useSession(), navigate = useNavigate()
  const [params] = useSearchParams()
  const [loginId, setLoginId] = useState(isDemo ? 'admin@example.test' : '')
  const [password, setPassword] = useState(isDemo ? 'demo-only' : '')
  async function login() {
    try {
      const next = await auth.adminLogin.mutateAsync({ loginId, password })
      setSession(next); setSelected(''); setPassword('')
      // 진입 URL이 아닌 인증 응답으로 역할과 시작 화면을 결정한다.
      navigate(next.startPath ?? roleStart(next.role), { replace: true })
    } catch { setPassword('') }
  }
  return <div className="admin-login-page">
    <header><Link to="/login" className="admin-login-brand" aria-label="사고뭉치 로그인"><Brand /><span className="admin-login-context">운영 관리</span></Link></header>
    <main>
      <div className="admin-login-heading"><p>관리자 전용</p><h1>관리자 로그인</h1>
        <p>등록된 운영 계정으로 로그인해 주세요.<br />로그인 후 부여된 권한에 맞는 메뉴가 열립니다.</p></div>
      <form onSubmit={(e) => { e.preventDefault(); void login() }}>
        {isDemo && <p className="admin-login-demo">개발 목업 · 실제 계정 정보를 입력하지 마세요.</p>}
        <label>로그인 ID<input aria-label="로그인 ID" autoComplete="username" value={loginId} onChange={(e) => setLoginId(e.target.value)} maxLength={254} required /></label>
        <label>비밀번호<input aria-label="비밀번호" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} maxLength={128} required /></label>
        <button type="submit" disabled={auth.adminLogin.isPending}>{auth.adminLogin.isPending ? '확인 중' : '로그인'}</button>
        <ErrorNotice error={auth.adminLogin.error} />
        {isDemo && <details><summary>권한별 시연 계정 보기</summary>
          <ul><li>전체: admin@example.test</li><li>콘텐츠: content@example.test</li><li>운영: ops@example.test</li><li>결제 조회: payment@example.test</li><li>환불: refund@example.test</li></ul>
          <p>시연 비밀번호: demo-only</p></details>}
      </form>
      {!isDemo && <section className="admin-login-oauth" aria-label="Google 관리자 인증">
        <p>Google 계정이 관리자로 등록되어 있다면</p>
        <a href="/api/v1/auth/google/authorize" className="admin-login-google">Google 계정으로 계속하기</a>
        {params.has('oauthError') && <p role="alert">{params.get('oauthError') === 'CANCELLED' ? 'Google 로그인을 취소했습니다.' : 'Google 로그인을 완료하지 못했습니다. 다시 시도해 주세요.'}</p>}
      </section>}
      <footer><Link to="/login">학부모·학생 로그인으로 돌아가기</Link></footer>
    </main>
  </div>
}
