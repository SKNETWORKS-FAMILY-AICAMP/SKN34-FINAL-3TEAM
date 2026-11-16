import { useDemoStudentEntry } from '../../data/studentDevice/queries.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

/**
 * DEV + MSW에서만 지연 로딩. 운영 인증에는 사용하지 않는다.
 * 가상 학생을 준비하면 시연 PIN을 안내하고, 키패드에 넣어 QR 등록 없이 체험한다.
 * 로그인 화면 위쪽 한 줄에 작게 둔다(#648: 시연 도구가 화면 높이를 차지해 390px에서 키패드가 밀리지 않게, 긴 설명 문단은 뺌).
 */
export default function DemoStudentEntry() {
  const prepare = useDemoStudentEntry()
  return <aside className="sl-demo-entry"><strong>학생 로그인 시연</strong>
    <button type="button" className="sl-demo-button" disabled={prepare.isPending} onClick={() => prepare.mutate()}>{prepare.isPending ? '준비하는 중' : '가상 학생으로 PIN 로그인 준비'}</button>
    {prepare.isSuccess && <p role="status">가상 학생이 준비되었습니다. PIN {prepare.data?.pin}을 입력해 주세요.</p>}
    <ErrorNotice error={prepare.error} />
  </aside>
}
