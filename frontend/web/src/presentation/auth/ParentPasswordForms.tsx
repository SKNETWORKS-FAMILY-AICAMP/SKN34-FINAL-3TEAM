import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useAuthentication } from '../../data/classroom/useClassroom.ts'
import { roleStart } from '../../domain/navigation.ts'
import type { Session } from '../../domain/classroom.ts'
import { useSession } from './sessionContext.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { PASSWORD_MAX, PASSWORD_MIN, PASSWORD_RECOVERY_NOTE, signupProblem } from '../../domain/parentAccount.ts'

function useEnter() {
  const { setSession, setSelected } = useSession(), navigate = useNavigate()
  return (next: Session) => {
    setSession(next); setSelected('')
    // 진입 URL이 아닌 인증 응답으로 시작 화면을 정한다(가입 직후에는 동의 화면).
    navigate(next.startPath ?? roleStart(next.role), { replace: true })
  }
}

/** 실제 모드 /login: Google과 나란히 두는 학부모 아이디 로그인 (#415). */
export function ParentIdLogin() {
  const auth = useAuthentication(), enter = useEnter()
  const [loginId, setLoginId] = useState(''), [password, setPassword] = useState('')
  return <form className="ux-login-id" aria-label="아이디 로그인" onSubmit={(e) => {
    e.preventDefault()
    void auth.parentLogin.mutateAsync({ loginId: loginId.trim(), password }).then(enter).catch(() => {}).finally(() => setPassword(''))
  }}>
    <p className="ux-login-or">또는 아이디로 로그인</p>
    <label className="cj-field">아이디
      <input aria-label="아이디" autoComplete="username" value={loginId} maxLength={30} onChange={(e) => setLoginId(e.target.value)} required />
    </label>
    <label className="cj-field">비밀번호
      <input aria-label="비밀번호" type="password" autoComplete="current-password" value={password} maxLength={PASSWORD_MAX} onChange={(e) => setPassword(e.target.value)} required />
    </label>
    <button className="cj-secondary" type="submit" disabled={auth.parentLogin.isPending}>{auth.parentLogin.isPending ? '확인 중' : '아이디로 로그인'}</button>
    <ErrorNotice error={auth.parentLogin.error} />
    <small>{PASSWORD_RECOVERY_NOTE}</small>
  </form>
}

/** 실제 모드 /signup: 아이디·비밀번호 가입. 동의·자녀 등록은 Google 가입과 같은 순서로 이어진다 (#415). */
export function ParentIdSignup() {
  const auth = useAuthentication(), enter = useEnter()
  const [loginId, setLoginId] = useState(''), [name, setName] = useState('')
  const [password, setPassword] = useState(''), [again, setAgain] = useState(''), [problem, setProblem] = useState<string | null>(null)
  return <form className="ws-form" aria-label="아이디로 가입" onSubmit={(e) => {
    e.preventDefault()
    const p = signupProblem(loginId, password, again, name)
    setProblem(p)
    if (p) return
    void auth.parentSignup.mutateAsync({ loginId: loginId.trim(), password, name: name.trim() })
      .then(enter).catch(() => {}).finally(() => { setPassword(''); setAgain('') })
  }}>
    <h2>아이디로 가입하기</h2>
    <label>아이디<input aria-label="가입 아이디" autoComplete="username" value={loginId} maxLength={30} onChange={(e) => setLoginId(e.target.value)} required /></label>
    <small>영문과 숫자 4~30자. 대문자는 소문자로 저장합니다.</small>
    <label>이름<input aria-label="보호자 이름" autoComplete="name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} required /></label>
    <label>비밀번호<input aria-label="가입 비밀번호" type="password" autoComplete="new-password" value={password} maxLength={PASSWORD_MAX} onChange={(e) => setPassword(e.target.value)} required /></label>
    <label>비밀번호 다시 입력<input aria-label="가입 비밀번호 확인" type="password" autoComplete="new-password" value={again} maxLength={PASSWORD_MAX} onChange={(e) => setAgain(e.target.value)} required /></label>
    <small>비밀번호는 {PASSWORD_MIN}~{PASSWORD_MAX}자입니다. {PASSWORD_RECOVERY_NOTE}</small>
    {problem && <p role="alert">{problem}</p>}
    <button className="cj-primary" type="submit" disabled={auth.parentSignup.isPending}>{auth.parentSignup.isPending ? '가입 중' : '가입하고 이용 동의로 이동'}</button>
    <ErrorNotice error={auth.parentSignup.error} />
    <p>가입하면 이용약관·개인정보 처리방침 동의와 자녀 등록을 이어서 진행합니다. 이미 가입했다면 <Link to="/login">로그인</Link>해 주세요.</p>
  </form>
}
