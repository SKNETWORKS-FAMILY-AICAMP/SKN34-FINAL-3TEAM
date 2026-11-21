import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { useChildPoints, useChildPosts } from '../../data/retention/queries.ts'
import type { Child } from '../../domain/classroom.ts'
import { POINT_EVENT_LABELS, POST_STATUS_LABELS, REACTION_LABELS, REACTIONS } from '../../domain/retention.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { communityConsentLink } from './consentLinks.ts'

const when = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'short', timeStyle: 'short' })

/**
 * 자녀의 참여 기록 (P20·P21, API 명세 2.9·2.10). 자녀 공유물·받은 반응·포인트만 본다.
 * 다른 학생의 글·잔액·순위는 보여 주지 않는다.
 */
export function ChildParticipation({ child, canReadOriginals = false }: { child: Child; canReadOriginals?: boolean }) {
  const [tab, setTab] = useState<'posts' | 'points'>('posts')
  const [postPage, setPostPage] = useState(0), [pointPage, setPointPage] = useState(0)
  const posts = useChildPosts(child.id, canReadOriginals)
  const points = useChildPoints(child.id, pointPage)
  const items = !posts.error ? posts.data ?? [] : []
  return <section className="pd-participation" aria-labelledby="participation-h">
    <header className="pd-explorer-heading"><h2 id="participation-h">참여 기록</h2>
      {points.data && !points.error && <span className="pd-point-balance">보유 포인트 <strong>{points.data.balance.toLocaleString()} P</strong></span>}
    </header>
    <nav className="pd-participation-tabs" aria-label="참여 기록 종류">
      <button type="button" aria-pressed={tab === 'posts'} onClick={() => setTab('posts')}>나눈 생각</button>
      <button type="button" aria-pressed={tab === 'points'} onClick={() => setTab('points')}>포인트 내역</button>
    </nav>
    {tab === 'points' ? <>
      <QueryFeedback query={points} />
      <div className="pd-table-scroll" role="region" aria-label="포인트 내역 목록" tabIndex={0}><table className="pd-explorer-table"><thead><tr><th>날짜</th><th>활동</th><th>포인트</th></tr></thead><tbody>
        {!points.error && points.data?.items.map((e, i) => <tr key={`${e.createdAt}-${i}`}><td>{when(e.createdAt)}</td><td>{POINT_EVENT_LABELS[e.eventType]}</td><td className="pd-point-amount">{e.amount > 0 ? '+' : ''}{e.amount.toLocaleString()} P</td></tr>)}
      </tbody></table></div>
      {points.data && !points.error && <nav className="pd-explorer-pagination" aria-label="포인트 페이지"><span>총 {points.data.totalElements}건</span><button type="button" disabled={pointPage === 0} onClick={() => setPointPage(pointPage - 1)}>이전</button><span>{pointPage + 1}</span><button type="button" disabled={(pointPage + 1) * points.data.size >= points.data.totalElements} onClick={() => setPointPage(pointPage + 1)}>다음</button></nav>}
      <p className="pd-date-note">포인트는 참여 기록이며 판정 결과나 순위와는 관계없습니다.</p>
    </> : <>
      <CommunityConsentStatus child={child} />
      {canReadOriginals ? <QueryFeedback query={posts} /> : <p>공유한 답변 원문은 아이가 학부모 공개를 켠 뒤 확인할 수 있습니다.</p>}
      {canReadOriginals && <div className="pd-shared-list">
        <div className="pd-shared-labels"><span>활동</span><span>공유 상태</span><span>날짜</span></div>
        {items.slice(postPage * 10, postPage * 10 + 10).map(p => <details key={p.postId} className="pd-shared-row"><summary><strong>{p.missionTitle}</strong><span className="pd-shared-status" data-status={p.status}>{POST_STATUS_LABELS[p.status]}</span><time>{p.createdAt ? when(p.createdAt) : '—'}</time><ChevronDown size={16} aria-hidden="true" /></summary>
          <div className="pd-shared-detail"><blockquote>{p.answer}</blockquote><p>받은 반응 · {REACTIONS.filter(r => p.reactions[r] > 0).map(r => `${REACTION_LABELS[r]} ${p.reactions[r]}`).join(' · ') || '없음'}</p></div>
        </details>)}
        {!posts.isPending && !posts.error && !items.length && <p>아직 나눈 생각이 없습니다.</p>}
        <nav className="pd-explorer-pagination" aria-label="나눈 생각 페이지"><span>총 {items.length}건</span><button type="button" disabled={postPage === 0} onClick={() => setPostPage(postPage - 1)}>이전</button><span>{postPage + 1}</span><button type="button" disabled={(postPage + 1) * 10 >= items.length} onClick={() => setPostPage(postPage + 1)}>다음</button></nav>
      </div>}
    </>}
  </section>
}

/**
 * 커뮤니티 선택 동의 상태와 동의 위치(계정·자녀 설정 › 공개·동의)로 가는 링크(#433).
 * 동의가 없으면 자녀의 "친구들에게 보여 줄게요"가 꺼져 있으므로 여기서 바로 안내한다.
 */
function CommunityConsentStatus({ child }: { child: Child }) {
  const history = useParentQuery(['consent-history'], (signal) => parentApi.consentHistory(signal))
  const { search } = useLocation()
  const current = history.data?.items.find((e) => e.document.kind === 'COMMUNITY' && e.studentId === child.id)
  const agreed = !!current && current.agreed && current.status === 'AGREED'
  const known = !!history.data && !history.error
  const message = child.guardianConsentRequired
    ? '법정대리인 동의를 먼저 마쳐 주세요. 그다음 커뮤니티 동의를 할 수 있습니다.'
    : !known
      ? '커뮤니티 동의 상태는 계정·자녀 설정의 공개·동의에서 확인할 수 있습니다.'
      : agreed
        ? '커뮤니티 이용에 동의했습니다. 친구 공개는 자녀가 직접 켜고 끕니다.'
        : '커뮤니티 이용에 아직 동의하지 않아 자녀가 친구 공개를 켤 수 없습니다.'
  return (
    <p role="note">
      {message}{' '}
      <Link className="cj-secondary" to={communityConsentLink(search)}>
        {child.guardianConsentRequired ? '법정대리인 동의하러 가기' : known && agreed ? '커뮤니티 동의 관리' : '커뮤니티 동의하기'}
      </Link>
    </p>
  )
}
