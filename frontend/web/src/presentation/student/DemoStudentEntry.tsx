import { useDemoStudentEntry } from '../../data/studentDevice/queries.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

/** DEV + MSW에서만 지연 로딩. 운영 인증에는 사용하지 않는다. */
export default function DemoStudentEntry() {
  const prepare = useDemoStudentEntry()
  return <aside className="device-notice"><strong>학생 로그인 시연</strong>
    <p>가상 학생을 준비하면 시연 PIN을 안내합니다. 아래 키패드에 입력해 QR 등록 없이 체험할 수 있습니다.</p>
    <button type="button" className="cj-secondary" disabled={prepare.isPending} onClick={() => prepare.mutate()}>{prepare.isPending ? '준비하는 중' : '가상 학생으로 PIN 로그인 준비'}</button>
    {prepare.isSuccess && <p role="status">가상 학생이 준비되었습니다. PIN {prepare.data?.pin}을 입력해 주세요.</p>}
    <ErrorNotice error={prepare.error} />
  </aside>
}
