import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { isDemo, useAuthentication } from '../../data/classroom/useClassroom.ts'
import { roleStart } from '../../domain/navigation.ts'
import { useSession } from '../auth/sessionContext.ts'
import { Brand, ErrorNotice } from '../shared/ClassroomParts.tsx'
import './admin-login.css'

export function AdminLoginPage() {
  const auth = useAuthentication(), { setSession, setSelected } = useSession(), navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState(isDemo ? 'admin@example.test' : '')
  const [password, setPassword] = useState(isDemo ? 'demo-only' : '')
  async function login() {
    try {
      const next = await auth.login.mutateAsync({ email, password })
      setSession(next); setSelected(''); setPassword('')
      // 진입 URL이 아닌 인증 응답으로 역할과 시작 화면을 결정한다.
      navigate(next.startPath ?? roleStart(next.role), { replace: true })
    } catch { setPassword('') }
  }
  return <div className="admin-login-page">
    <header><Link to="/login" className="admin-login-brand" aria-label="사고뭉치 로그인"><Brand /><span className="admin-login-context">운영 관리</span></Link></header>
    <main>
      <div className="admin-login-heading"><p>관리자 전용</p><h1>관리자 로그인</h1>
        <p>승인된 운영 계정으로 로그인해 주세요.<br />로그인 후 부여된 권한에 맞는 메뉴가 열립니다.</p></div>
      {isDemo ? <form onSubmit={(e) => { e.preventDefault(); void login() }}>
        <p className="admin-login-demo">개발 목업 · 실제 계정 정보를 입력하지 마세요.</p>
        <label>이메일<input aria-label="이메일" type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>비밀번호<input aria-label="비밀번호" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button type="submit" disabled={auth.login.isPending}>{auth.login.isPending ? '확인 중' : '시연 계정으로 로그인'}</button>
        <ErrorNotice error={auth.login.error} />
        <details><summary>권한별 시연 계정 보기</summary>
          <ul><li>전체: admin@example.test</li><li>콘텐츠: content@example.test</li><li>운영: ops@example.test</li><li>결제 조회: payment@example.test</li><li>환불: refund@example.test</li></ul>
          <p>시연 비밀번호: demo-only</p></details>
      </form> : <section className="admin-login-oauth" aria-label="관리자 인증">
        <a href="/api/v1/auth/google/authorize" className="admin-login-submit">Google 계정으로 계속하기</a>
        <p>서버에서 관리자 역할과 승인 권한을 확인합니다.</p>
        {params.has('oauthError') && <p role="alert">{params.get('oauthError') === 'CANCELLED' ? 'Google 로그인을 취소했습니다.' : 'Google 로그인을 완료하지 못했습니다. 다시 시도해 주세요.'}</p>}
      </section>}
      <footer><Link to="/login">학부모·학생 로그인으로 돌아가기</Link></footer>
    </main>
  </div>
}
