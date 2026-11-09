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
export function ChildParticipation({ child }: { child: Child }) {
  const posts = useChildPosts(child.id)
  const points = useChildPoints(child.id)
  return (
    <section className="ws-card" aria-labelledby="participation-h">
      <h2 id="participation-h">{child.nickname}의 참여 기록</h2>
      <h3>포인트</h3>
      <QueryFeedback query={points} />
      {points.data && !points.error && (
        <>
          <p>지금 {points.data.balance}포인트 · 참여한 만큼 쌓이며 판정 결과·순위와는 관계없습니다.</p>
          <ul>
            {points.data.items.slice(0, 5).map((e, i) => (
              <li key={`${e.createdAt}-${i}`}>
                {when(e.createdAt)} · {POINT_EVENT_LABELS[e.eventType]} · {e.amount > 0 ? `+${e.amount}` : e.amount}
              </li>
            ))}
          </ul>
        </>
      )}
      <h3>커뮤니티에 나눈 생각</h3>
      <CommunityConsentStatus child={child} />
      <QueryFeedback query={posts} />
      {posts.data && !posts.error && !posts.data.length && (
        <p>아직 나눈 생각이 없습니다. 커뮤니티 공개는 보호자 동의 후 자녀가 직접 켭니다.</p>
      )}
      {posts.data?.map((p) => (
        <article className="ws-card" key={p.postId}>
          <p>
            {p.missionTitle} · {POST_STATUS_LABELS[p.status]}
          </p>
          <blockquote>{p.answer}</blockquote>
          <p>
            받은 반응 ·{' '}
            {REACTIONS.filter((r) => p.reactions[r] > 0)
              .map((r) => `${REACTION_LABELS[r]} ${p.reactions[r]}`)
              .join(' · ') || '없음'}
          </p>
        </article>
      ))}
    </section>
  )
}

/**
 * 커뮤니티 선택 동의 상태와 동의 위치(정보 관리 › 동의 이력·철회)로 가는 링크(#433).
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
      ? '커뮤니티 동의 상태는 정보 관리에서 확인할 수 있습니다.'
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
