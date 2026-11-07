import { useChildPoints, useChildPosts } from '../../data/retention/queries.ts'
import type { Child } from '../../domain/classroom.ts'
import { POINT_EVENT_LABELS, POST_STATUS_LABELS, REACTION_LABELS, REACTIONS } from '../../domain/retention.ts'
import { QueryFeedback } from '../common/Workspace.tsx'

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
