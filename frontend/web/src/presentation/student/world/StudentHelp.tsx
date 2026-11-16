import { Link, useSearchParams } from 'react-router'
import { useParentQuery } from '../../../data/parent/queries.ts'
import { serviceApi } from '../../../data/serviceApi.ts'
import { Help, Notices, ServiceContent, Support } from '../../service/ServiceCenter.tsx'
import { SupportResults } from '../../support/SupportResults.tsx'

export type HelpPage = 'help' | 'support' | 'results' | 'notices' | 'notifications'

/**
 * 학생 도움말·문의·공지·알림(#648, 시안 Help). 예전 고객센터 틀 대신 학생 틀(StudentWorld) 안에 그린다.
 * 도움말·문의는 한 화면 2단(왼쪽 자주 묻는 질문·공지, 오른쪽 문의·오류 신고). 요청·접수 동작은 고객센터와 같은 부품을 그대로 쓴다.
 * 알림 링크의 /student/support?reportId=…·inquiryId=…는 처리 결과를 바로 연다(예전 SupportEntry와 같음).
 */
export function StudentHelp({ page }: { page: HelpPage }) {
  const [params] = useSearchParams()
  if (page === 'results' || (page === 'support' && (params.has('reportId') || params.has('inquiryId'))))
    return <main className="st-paper st-sheet st-help-single"><SupportResults /></main>
  if (page === 'notices') return <main className="st-paper st-sheet st-help-single"><Notices /><Link className="st-help-link" to="/student/help">← 이용 도움말</Link></main>
  if (page === 'notifications')
    return <main className="st-paper st-sheet st-help-single"><h1>알림</h1><ServiceContent page="notifications" /><Link className="st-help-link" to="/student/help">← 이용 도움말</Link></main>
  return (
    <main className="st-paper st-sheet st-help">
      <section className="st-help-faq" aria-label="이용 도움말">
        <Help role="STUDENT" />
        <NoticeBox />
      </section>
      <section className="st-help-support" aria-label="문의·오류 신고">
        <Support level="h2" />
        <Link className="st-help-link" to="/student/support/results">신고·문의 처리 결과</Link>
      </section>
    </main>
  )
}

/** 공지·점검 한 줄 안내(시안 Help 왼쪽 아래). 공지 화면(Notices)과 같은 조회 키를 써서 다시 받지 않는다 */
function NoticeBox() {
  const q = useParentQuery(['notices'], serviceApi.notices)
  const first = q.data?.items[0]
  return (
    <p className="st-help-notice">
      <b>공지·점검 안내</b> ·{' '}
      {q.isPending ? '공지를 확인하고 있어요.' : q.error ? '공지를 불러오지 못했어요.' : first ? first.title : '현재 공개된 공지가 없어요.'}
      {first && <> <Link to="/student/notices">공지 모두 보기</Link></>}
    </p>
  )
}
