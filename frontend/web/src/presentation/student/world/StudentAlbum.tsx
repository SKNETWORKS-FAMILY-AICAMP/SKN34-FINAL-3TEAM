import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Images, Sparkles } from 'lucide-react'
import { useAlbum, useEpisode, useMarkFramesSeen } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { thinkingLabels } from '../../../domain/classroom.ts'
import { DAY_LABELS, episodeKey, weekLabel } from '../../../domain/retention.ts'
import type { AlbumItem } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import './room.css'

const PAGE_SIZE = 12
const day = (iso: string) => new Date(iso).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric' })
const notFound = (e: unknown) => e instanceof ApiError && e.problem.code === 'THEME_FRAME_NOT_FOUND'

/** 액자 그림: 회차 이미지가 있으면 그것, 없으면 테마 이름으로 색을 고른 작은 풍경 */
function FrameArt({ item, example = false }: { item: { themeId: string; title: string; imageUrl: string | null }; example?: boolean }) {
  if (item.imageUrl) return <img className="st-frame-art" src={item.imageUrl} alt="" />
  const hues = ['#9CCB8C', '#7FC8D8', '#E9B949', '#F2B8A0', '#B8C2CC']
  const hue = hues[[...item.themeId].reduce((n, c) => n + c.charCodeAt(0), 0) % hues.length]
  return (
    <svg className="st-frame-art" viewBox="0 0 120 80" aria-hidden="true" focusable="false">
      <rect width="120" height="80" fill={example ? '#EDE6D6' : '#C6EAE1'} />
      <circle cx="92" cy="20" r="9" fill={example ? '#D7CDB8' : '#F2C14E'} />
      <path d="M0 80 L30 38 L52 58 L76 30 L120 80Z" fill={example ? '#CFC4AC' : hue} stroke="#1F2421" strokeWidth="2.5" />
    </svg>
  )
}

/**
 * 추억 앨범(/student/album, P27·FN-RET-10·11, #561). 보유 액자 회차만 최근순으로 보인다
 * (진행 중인 주·추가 문제는 서버가 뺌). 들어오면 새 액자를 안내하고 확인(seen)을 남긴다.
 */
export function StudentAlbum({ child, onOpen, onRoom }: {
  child: Child
  onOpen: (item: { themeId: string; weekStart: string }) => void
  onRoom: () => void
}) {
  const [page, setPage] = useState(0)
  const album = useAlbum(child.id, page, PAGE_SIZE)
  const seen = useMarkFramesSeen(child.id)
  // 이번 방문에서 안내한 새 액자. 확인을 남긴 뒤에도 이 화면에서는 "새 액자"로 보여 준다
  const [fresh, setFresh] = useState<AlbumItem[] | null>(null)
  const announced = useRef(false)
  useEffect(() => {
    if (announced.current || !album.data) return
    announced.current = true
    const unseen = album.data.items.filter((i) => !i.seen)
    setFresh(unseen)
    if (unseen.length) seen.mutate(unseen.map(({ themeId, weekStart }) => ({ themeId, weekStart })))
  }, [album.data, seen])
  const freshKeys = new Set((fresh ?? []).map(episodeKey))
  const data = album.error ? undefined : album.data
  const pages = data ? Math.max(1, Math.ceil(data.totalElements / data.size)) : 1

  return (
    <main className="st-paper st-sheet st-album-page">
      <div className="st-sheet-head">
        <h1><Images aria-hidden="true" /> 추억 앨범</h1>
        <p>한 주 테마 문제 다섯 개를 모두 마무리하면 그 주의 기념 액자가 생겨요.</p>
      </div>
      <button type="button" className="st-button st-room-back" onClick={onRoom}><ArrowLeft aria-hidden="true" /> 내 방으로</button>
      {album.isPending && <p role="status">앨범을 펼치고 있어요.</p>}
      <ErrorNotice error={album.error} retry={() => void album.refetch()} />
      {!!fresh?.length && (
        <section className="st-new-frames" role="status" aria-label="새 액자 안내">
          <Sparkles aria-hidden="true" />
          <p><strong>새 액자가 생겼어요!</strong> {fresh.map((f) => f.title || '이름 없는 테마').join(', ')}</p>
          <button type="button" className="st-button st-primary" onClick={onRoom}>추억의 벽에 걸러 가기</button>
        </section>
      )}
      {data && data.totalElements === 0 && (
        <section className="st-album-empty" aria-label="빈 앨범 안내">
          <p>아직 기념 액자가 없어요. 이번 주 테마 문제를 하나씩 마무리해 볼까?</p>
          <figure className="st-frame-card st-frame-example">
            <FrameArt item={{ themeId: 'example', title: '', imageUrl: null }} example />
            <figcaption><span className="st-badge">예시</span> 이런 액자가 앨범에 모여요</figcaption>
          </figure>
        </section>
      )}
      {data && data.items.length > 0 && (
        <ul className="st-album-grid" aria-label="보유한 기념 액자">
          {data.items.map((item) => (
            <li key={episodeKey(item)}>
              <button type="button" className="st-frame-card" onClick={() => onOpen(item)}>
                <FrameArt item={item} />
                <strong>{item.title || '이름 없는 테마'}</strong>
                <small>{weekLabel(item.weekStart)} · {day(item.awardedAt)}에 받음</small>
                <span className="st-frame-tags">
                  {(freshKeys.has(episodeKey(item)) || !item.seen) && <span className="st-badge st-badge-new">새 액자</span>}
                  {item.displayed && <span className="st-badge">벽에 걸림</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {data && pages > 1 && (
        <nav className="st-album-pages" aria-label="앨범 쪽">
          <button type="button" className="st-button" disabled={page === 0} onClick={() => setPage(page - 1)}>앞 쪽</button>
          <span>{page + 1} / {pages}</span>
          <button type="button" className="st-button" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>다음 쪽</button>
        </nav>
      )}
    </main>
  )
}

/**
 * 회차 상세(/student/album/:themeId/:weekStart). 다섯 문제는 기존 시도 상세(처음·보완 답변 비교)로 연다.
 * 종료 이야기·정답은 그 주 엔딩을 본 학생만 보인다(P23).
 */
export function StudentEpisode({ child, themeId, weekStart, onBack, onAttempt }: {
  child: Child
  themeId: string
  weekStart: string
  onBack: () => void
  onAttempt: (attemptId: string) => void
}) {
  const episode = useEpisode(child.id, themeId, weekStart)
  const e = episode.error ? undefined : episode.data
  return (
    <main className="st-paper st-sheet st-album-page">
      <button type="button" className="st-button st-room-back" onClick={onBack}><ArrowLeft aria-hidden="true" /> 앨범으로</button>
      {episode.isPending && <p role="status">그 주 기록을 펼치고 있어요.</p>}
      {notFound(episode.error) ? (
        <p role="alert">이 액자를 찾지 못했어요. 앨범에서 다시 골라 주세요.</p>
      ) : (
        <ErrorNotice error={episode.error} retry={() => void episode.refetch()} />
      )}
      {e && (
        <>
          <div className="st-sheet-head">
            <h1>{e.title || '이름 없는 테마'}</h1>
            <p>{weekLabel(e.weekStart)} · {day(e.awardedAt)}에 기념 액자를 받았어요.</p>
          </div>
          <ol className="st-episode-missions" aria-label="그 주 문제">
            {e.missions.map((m) => (
              <li key={m.day}>
                <span className="st-day">{DAY_LABELS[m.day]}</span>
                <div>
                  <strong>{m.title || '문제'}</strong>
                  {m.thinkingType && <small>{thinkingLabels[m.thinkingType]}</small>}
                </div>
                {m.attemptId ? (
                  <button type="button" className="st-button" onClick={() => onAttempt(m.attemptId!)}>그때 기록 보기</button>
                ) : (
                  <span className="st-meta">남은 기록이 없어요</span>
                )}
              </li>
            ))}
          </ol>
          <section className="st-episode-ending" aria-label="그 주 이야기의 끝">
            <h2>이야기의 끝</h2>
            {e.ending.seen ? (
              <>
                {e.ending.outro && <p>{e.ending.outro}</p>}
                {e.ending.answer && <p><strong>큰 질문의 답:</strong> {e.ending.answer}</p>}
              </>
            ) : (
              <p className="st-meta">그 주에는 이야기의 끝을 보지 못해서 끝 이야기와 답은 숨겨 두었어요.</p>
            )}
          </section>
        </>
      )}
    </main>
  )
}
