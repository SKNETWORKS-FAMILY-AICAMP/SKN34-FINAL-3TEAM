import { isDemo } from '../../data/classroom/useClassroom.ts'

/** Device/PIN endpoints remain follow-up work; never fabricate a successful login. */
export function StudentEntryPage() {
  return <main className="ws-card">
    <h1>학생 로그인</h1>
    <p>학생 로그인은 만료되거나 새로고침하면 다시 진행해야 합니다.</p>
    <p role="status">등록된 기기에서 프로필과 PIN으로 들어오는 기능을 준비하고 있습니다.</p>
    <p>지금은 학부모가 로그인한 뒤 자녀를 선택해 함께 시작할 수 있습니다.</p>
    <a className="cj-primary" href={isDemo ? '/login' : '/api/v1/auth/google/authorize'}>학부모와 함께 시작하기</a>
  </main>
}
