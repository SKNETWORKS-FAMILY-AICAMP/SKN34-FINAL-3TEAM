import { useState } from 'react'
import { Flag, House } from 'lucide-react'
import { useStudentHome } from '../../../data/classroom/useClassroom.ts'
import {
  useCommunitySettings,
  useMissionPosts,
  useMyPosts,
  useReact,
  useLookItems,
  useReportPost,
} from '../../../data/retention/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { studentThinkingLabels } from '../../../domain/classroom.ts'
import { POST_STATUS_LABELS, REACTION_LABELS, REACTIONS, wornAssets } from '../../../domain/retention.ts'
import type { CommunityPost } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { FriendRoom } from './FriendRoom.tsx'
import './retention.css'

/**
 * 친구 생각 (커뮤니티, P20, API 명세 2.9).
 * 마무리한 미션에서만 같은 미션 친구들의 답을 볼 수 있고, 정해진 반응 네 가지만 남긴다.
 * 순서는 무작위이고 반응 수·순위·인기순은 보여 주지 않는다(받은 반응 수는 내 글에서만).
 * #648 시안 Community: 왼쪽 미션 목록, 오른쪽 친구들 글(그 칸 안에서만 스크롤). "내가 나눈 생각"은 오른쪽 칸을 바꿔 보여 준다.
 * 친구 방 놀러 가기(#709, FN-RET-14): 글 카드의 "놀러 가기"를 누르면 이 화면 자리에 친구 방을 보여 준다(주소는 그대로, 기준안).
 * 친구 생각 화면은 지우지 않고 숨겨 두어 돌아오면 고른 미션·같은 seed 순서·스크롤 위치가 그대로다.
 */
export function StudentCommunity({ child, onSettings, initialMission = null }: {
  child: Child
  onSettings: () => void
  /** 처음 고를 미션(`?mission=`, 미션 완료 화면 "같은 미션 친구 생각 보기" #807). 마무리한 미션이 아니면 무시 */
  initialMission?: string | null
}) {
  const home = useStudentHome(child)
  const settings = useCommunitySettings(child.id)
  const mine = useMyPosts(child.id)
  const finished = (home.data?.missions ?? []).filter((m) => m.status === 'COMPLETED')
  const [missionId, setMissionId] = useState<string | null>(initialMission)
  const [showMine, setShowMine] = useState(false)
  const selected = (missionId && finished.some((m) => m.id === missionId) ? missionId : null) ?? finished[0]?.id ?? null
  // 같은 화면에서는 같은 순서로 보이게 seed를 한 번 정한다.
  const [seed] = useState(() => crypto.randomUUID().slice(0, 8))
  const posts = useMissionPosts(child.id, selected, seed)
  // 놀러 간 친구 글: 글 번호와 별명만 둔다(학생 ID는 응답에도 없음, NFR-SEC-02)
  const [visiting, setVisiting] = useState<{ postId: string; nickname: string } | null>(null)
  return (
    <>
    {visiting && <FriendRoom child={child} postId={visiting.postId} nickname={visiting.nickname} onBack={() => setVisiting(null)} />}
    <main className="st-paper st-sheet st-community" hidden={!!visiting}>
      <section className="st-community-left" aria-labelledby="community-title">
        <h1 id="community-title" className="st-title-mix">
          친구 <span>생각</span>
        </h1>
        <p className="st-meta">내가 마무리한 미션만 친구들 생각을 볼 수 있어요.</p>
        <ErrorNotice error={home.error} retry={() => void home.refetch()} />
        {home.isSuccess && finished.length === 0 && (
          <p role="status">아직 마무리한 미션이 없어요. 미션을 끝까지 하면 친구들 생각이 열려요.</p>
        )}
        {finished.length > 0 && (
          <div className="st-community-missions" role="group" aria-labelledby="community-pick-h">
            <strong id="community-pick-h">어떤 미션을 볼까요?</strong>
            <ul className="st-scroll">
              {finished.map((m) => (
                <li key={m.id}>
                  <button type="button" aria-pressed={!showMine && m.id === selected}
                    onClick={() => { setMissionId(m.id); setShowMine(false) }}>
                    <b>{m.title}</b>
                    <small>{studentThinkingLabels[m.thinkingType]} · {m.subject}</small>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <button type="button" className="st-pill-link" aria-pressed={showMine} onClick={() => setShowMine((v) => !v)}>
          {showMine ? '친구들 생각 보기' : '내가 나눈 생각 보기'} <span aria-hidden="true">→</span>
        </button>
        <p className="st-community-note">
          {settings.data && !settings.data.enabled ? (
            <>
              내 답은 지금 친구들에게 보이지 않아요.{' '}
              <button type="button" className="st-link" onClick={onSettings}>
                공개 설정
              </button>
              에서 바꿀 수 있어요.
            </>
          ) : (
            <>반응을 남기면 +1 포인트(하루 5번까지). 내 답 공개는 설정에서 바꿀 수 있어요.</>
          )}
        </p>
      </section>
      <section className="st-community-right" aria-label={showMine ? '내가 나눈 생각' : '친구들 생각'}>
        {showMine ? (
          <>
            <h2 id="mine-h">내가 나눈 생각</h2>
            <div className="st-scroll">
              <ErrorNotice error={mine.error} retry={() => void mine.refetch()} />
              {mine.isSuccess && mine.data.length === 0 && <p className="st-meta">아직 나눈 생각이 없어요.</p>}
              <ul className="st-posts">
                {mine.data?.map((p) => (
                  <li key={p.postId} className="st-post">
                    <p className="st-kicker">
                      {p.missionTitle} · {POST_STATUS_LABELS[p.status]}
                    </p>
                    <p className="st-post-answer">{p.answer}</p>
                    <p className="st-meta">
                      받은 반응:{' '}
                      {REACTIONS.filter((r) => p.reactions[r] > 0)
                        .map((r) => `${REACTION_LABELS[r]} ${p.reactions[r]}`)
                        .join(' · ') || '아직 없어요'}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </>
        ) : (
          <>
            <h2 className="st-visually-hidden">친구들 생각</h2>
            <div className="st-scroll">
              {/* 마무리한 미션이 없으면 오른쪽 칸이 통째로 비지 않게 안내(점검 2026-11-15) */}
              {!selected && home.isSuccess && (
                <p className="st-community-empty">미션을 하나 끝까지 하면 여기에서 친구들 생각을 볼 수 있어요.</p>
              )}
              {posts.isPending && selected && <p role="status">친구들 생각을 불러오고 있어요.</p>}
              <ErrorNotice error={posts.error} retry={() => void posts.refetch()} />
              {posts.isSuccess && posts.data.length === 0 && <p role="status">이 미션에는 아직 친구들 생각이 없어요.</p>}
              <ul className="st-posts">
                {posts.data?.map((p) => (
                  <PostCard key={p.postId} child={child} post={p}
                    onVisit={() => setVisiting({ postId: p.postId, nickname: p.author.nickname })} />
                ))}
              </ul>
            </div>
          </>
        )}
      </section>
    </main>
    </>
  )
}

function PostCard({ child, post, onVisit }: { child: Child; post: CommunityPost; onVisit: () => void }) {
  const react = useReact(child.id)
  const report = useReportPost(child.id)
  const [reporting, setReporting] = useState(false)
  const [comment, setComment] = useState('')
  const [reportKey] = useState(() => crypto.randomUUID())
  // 작성자 착용 그림(#635): 응답의 착용 아이템 키를 아이템 목록 그림과 맞춤. 목록에 없는 아이템(판매 중단 등)은 그 칸만 빠짐
  const items = useLookItems(child.id)
  const worn = wornAssets(post.author.equipped, items.error ? undefined : items.data)
  return (
    <li className="st-post">
      <p className="st-post-author">
        <Companion kind={post.author.companion} size={40} decorative worn={worn} />
        <strong>{post.author.nickname}</strong>
        <button type="button" className="st-pill-link st-post-visit" onClick={onVisit}
          aria-label={`${post.author.nickname}의 방에 놀러 가기`}>
          <House aria-hidden="true" size={18} /> 놀러 가기
        </button>
      </p>
      <p className="st-post-answer">{post.answer}</p>
      <div className="st-reactions" role="group" aria-label={`${post.author.nickname}의 생각에 반응하기`}>
        {REACTIONS.map((r) => {
          const on = post.myReactions.includes(r)
          return (
            <button
              type="button"
              key={r}
              className="st-reaction"
              aria-pressed={on}
              disabled={react.isPending}
              onClick={() => react.mutate({ postId: post.postId, reaction: r, on: !on })}
            >
              {REACTION_LABELS[r]}
            </button>
          )
        })}
      </div>
      <ErrorNotice error={react.error} />
      <div className="st-post-report">
      {report.isSuccess ? (
        <p role="status">신고를 받았어요. 확인하는 동안 이 글은 숨겨져요.</p>
      ) : reporting ? (
        <form
          className="st-report"
          onSubmit={(e) => {
            e.preventDefault()
            report.mutate({ postId: post.postId, comment, key: reportKey })
          }}
        >
          <label>
            어떤 점이 이상했나요? (안 써도 돼요)
            <textarea value={comment} maxLength={500} onChange={(e) => setComment(e.target.value)} />
          </label>
          <button type="submit" className="st-button" disabled={report.isPending}>
            신고하기
          </button>
          <button type="button" className="st-link" onClick={() => setReporting(false)}>
            그만두기
          </button>
          <ErrorNotice error={report.error} />
        </form>
      ) : (
        <button type="button" className="st-link" onClick={() => setReporting(true)}>
          <Flag aria-hidden="true" size={14} /> 이상한 글 신고
        </button>
      )}
      </div>
    </li>
  )
}
