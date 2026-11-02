import { Link } from 'react-router'
import './service.css'
export function LoginHelp() {
  return <main id="class-journal" style={{maxWidth:760,margin:'40px auto',padding:24}}><div className="svc-page"><h1>로그인이 어려우신가요?</h1><section className="ws-card"><h2>학부모·관리자</h2><p>처음 이용한 Google 계정으로 로그인해 주세요. 다른 계정을 선택하면 기존 자녀 연결이 표시되지 않을 수 있습니다.</p><div className="ws-actions"><a href="/api/v1/auth/google/authorize">Google 로그인 다시 시작</a><a href="https://accounts.google.com/signin/recovery" target="_blank" rel="noreferrer">Google 계정 복구</a></div><p>계정 복구는 Google의 본인 확인 절차를 따릅니다. 이 서비스에서 Google 비밀번호를 입력받지 않습니다.</p></section><section className="ws-card"><h2>학생 기기</h2><p>등록 코드가 만료됐거나 기기 등록이 해제되었다면 보호자에게 새 코드를 받아 주세요. PIN이 잠겼다면 보호자 화면에서 본인 확인 후 PIN을 다시 정해야 합니다.</p><Link to="/student/login">학생 기기 등록·PIN 화면</Link></section><Link to="/login">로그인 화면으로</Link></div></main>
}
