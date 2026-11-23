import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowLeft } from 'lucide-react'
import { useAlbum, useEpisode, useMarkFramesSeen, useWeeklyTheme } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import { useMission } from '../../../data/classroom/useClassroom.ts'
import type { Child } from '../../../domain/classroom.ts'
import { studentThinkingLabels } from '../../../domain/classroom.ts'
import { DAY_LABELS, episodeKey, weekLabel } from '../../../domain/retention.ts'
import { thinkingHue } from '../../../domain/studentLook.ts'
import type { AlbumItem } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import { MemorySearch } from './MemorySearch.tsx'
import { MemoryBookPanel } from './MemoryBookPanel.tsx'
import './room.css'
import { FrameScene } from './FrameScene.tsx'

const PAGE_SIZE = 12
const day = (iso: string) => new Date(iso).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric' })
const notFound = (e: unknown) => e instanceof ApiError && e.problem.code === 'THEME_FRAME_NOT_FOUND'

/** 액자 그림: 회차 이미지가 있으면 그것, 없으면 회차마다 다른 장면(FrameScene, 2026-11-16) */
function FrameArt({ item, example = false }: { item: { themeId: string; title: string; imageUrl: string | null }; example?: boolean }) {
  if (item.imageUrl) return <img className="st-frame-art" src={item.imageUrl} alt="" />
  return <FrameScene className="st-frame-art" themeId={item.themeId} title={item.title} muted={example} />
}

/** 받은 액자 카드가 번갈아 살짝 기운 각도(시안 Album) */
const TILTS = ['-1.5deg', '1.5deg', '-1deg', '1deg', '-0.5deg', '0.8deg']

/**
 * 추억 앨범(/student/album, P27·FN-RET-10·11, #561). 보유 액자 회차만 최근순으로 보인다
 * (진행 중인 주·추가 문제는 서버가 뺌). 들어오면 새 액자를 안내하고 확인(seen)을 남긴다.
 * #648 시안 Album(2026-11-16): "← 내 방"·"기념 액자 N개", 큰 제목, "받은 기념 액자" — 기울인 나무 액자 카드(새 액자 도장·벽에 걸림),
 * 끝에 이번 주 액자 자리(점선). 제목 아래 "기억으로 찾기"는 #567(추억 검색) `MemorySearch`.
 * PC 1440×900 한 화면, 액자 목록만 칸 안에서 스크롤.
 */
export function StudentAlbum({ child, onOpen, onRoom }: {
  child: Child
  onOpen: (item: { themeId: string; weekStart: string }) => void
  onRoom: () => void
}) {
  const { companion } = useLook()
  const [page, setPage] = useState(0)
  const album = useAlbum(child.id, page, PAGE_SIZE)
  const weekly = useWeeklyTheme(child.id)
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
  // 이번 주 액자 자리: 이번 주 테마가 있고 그 회차가 아직 앨범에 없을 때(진행 중인 주는 서버가 앨범에서 뺌)
  const theme = weekly.error ? null : weekly.data
  const solved = theme ? theme.days.filter((d) => d.attemptStatus === 'COMPLETED').length : 0
  const showNext = !!theme && page === 0 && !data?.items.some((i) => i.themeId === theme.themeId && i.weekStart === theme.weekStart)

  return (
    <main className="st-paper st-sheet st-album-page">
      <nav className="st-album-nav" aria-label="앨범 메뉴">
        <button type="button" className="st-pill-back" onClick={onRoom}><ArrowLeft aria-hidden="true" /> 내 방</button>
        {data && <span className="st-album-count">기념 액자 {data.totalElements.toLocaleString('ko-KR')}개</span>}
      </nav>
      <h1 className="st-album-title"><span>추억 </span><span>앨범</span></h1>
      <MemorySearch child={child} onOpen={onOpen} />
      {album.isPending && <p role="status">앨범을 펼치고 있어요.</p>}
      <ErrorNotice error={album.error} retry={() => void album.refetch()} />
      {!!fresh?.length && (
        <section className="st-new-frames" role="status" aria-label="새 액자 안내">
          <p><strong>새 액자가 생겼어요!</strong> {fresh.map((f) => `「${f.title || '이름 없는 테마'}」`).join(', ')}</p>
          <button type="button" className="st-album-go" onClick={onRoom}>추억의 벽에 걸러 가기</button>
        </section>
      )}
      {data && (
        <section className="st-album-shelf" aria-labelledby="album-frames-h">
          <h2 id="album-frames-h"><span>받은 </span>기념 액자</h2>
          <ul className="st-album-grid" aria-label="보유한 기념 액자">
            {data.items.map((item, n) => {
              const isNew = freshKeys.has(episodeKey(item)) || !item.seen
              return (
                <li key={episodeKey(item)} style={{ '--st-tilt': TILTS[n % TILTS.length] } as CSSProperties}>
                  <button type="button" className="st-album-card" onClick={() => onOpen(item)}>
                    <span className="st-album-frame"><FrameArt item={item} /></span>
                    {isNew && <span className="st-album-stamp">새 액자</span>}
                    <strong>{item.title || '이름 없는 테마'}</strong>
                    <small>{weekLabel(item.weekStart)} · {item.displayed ? <b>벽에 걸림</b> : '아직 안 걸었어요'}</small>
                  </button>
                </li>
              )
            })}
            {showNext && (
              <li className="st-album-next" aria-label="이번 주 액자 자리">
                <Companion kind={companion} size={86} decorative />
                <strong>{theme.title || '이번 주 테마'}</strong>
                <span>{solved >= 5 ? '다섯 문제를 모두 마쳤어요! 이번 주가 끝나면 여기에 생겨요' : `이번 주 다섯 문제를 마치면 여기에 생겨요 (지금 ${solved} / 5)`}</span>
              </li>
            )}
            {data.totalElements === 0 && !showNext && (
              <li className="st-album-next" aria-label="빈 앨범 안내">
                <Companion kind={companion} size={86} decorative />
                <strong>아직 기념 액자가 없어요</strong>
                <span>한 주 테마 문제 다섯 개를 모두 마무리하면 그 주의 기념 액자가 생겨요.</span>
              </li>
            )}
          </ul>
          {pages > 1 && (
            <nav className="st-album-pages" aria-label="앨범 쪽">
              <button type="button" className="st-pill-back" disabled={page === 0} onClick={() => setPage(page - 1)}>앞 쪽</button>
              <span>{page + 1} / {pages}</span>
              <button type="button" className="st-pill-back" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>다음 쪽</button>
            </nav>
          )}
        </section>
      )}
    </main>
  )
}

/**
 * 그 주 문제 칸 그림: 문제마다 있는 장면 그림(테마 문제는 그날 장면 그림이 미션 그림, ThemeDraftRules)을 기존 미션 상세 조회로 읽는다.
 * 미션을 못 읽거나(게시 중단 등) 그림이 없으면 요일 글자 칸(사용자 의견 2026-11-16 "원래 문제마다 그림 있으니까")
 */
function MissionTile({ child, missionId, day }: { child: Child; missionId: string; day: string }) {
  const mission = useMission(missionId, child)
  const src = mission.data?.staticSceneUri ?? mission.data?.sceneUri
  if (!src) return <span className="st-episode-tile" aria-hidden="true">{day}</span>
  return (
    <span className="st-episode-tile has-art" aria-hidden="true">
      <img src={src} alt="" />
      <b>{day}</b>
    </span>
  )
}

/**
 * 회차 상세(/student/album/:themeId/:weekStart). 다섯 문제는 기존 시도 상세(처음·보완 답변 비교)로 연다.
 * 종료 이야기·정답은 그 주 엔딩을 본 학생만 보인다(P23).
 * #648 시안 AlbumDetail: 큰 액자 + 제목, 아래 다섯 문제 카드 한 줄. 한 화면에 맞추지 않고 페이지 전체를 내려 본다
 * (예전에는 PC 한 화면이라 제목·엔딩 글이 오른쪽 칸 안에서만 스크롤됨 → 사용자 의견 2026-11-16 "위에 글이 스크롤 너무 불편해").
 */
export function StudentEpisode({ child, themeId, weekStart, onBack, onRoom, onAttempt }: {
  child: Child
  themeId: string
  weekStart: string
  onBack: () => void
  onRoom: () => void
  onAttempt: (attemptId: string) => void
}) {
  const episode = useEpisode(child.id, themeId, weekStart)
  // 그림: 회차 응답의 시작 이야기 그림(api-spec 4.1.4), 없으면 앨범 목록(내 방과 같은 첫 50개, 대개 캐시)의 그림
  const albumItems = useAlbum(child.id, 0, 50).data?.items
  const e = episode.error ? undefined : episode.data
  const imageUrl = e?.imageUrl ?? albumItems?.find((i) => i.themeId === themeId && i.weekStart === weekStart)?.imageUrl ?? null
  return (
    <main className="st-paper st-sheet st-episode-page">
      <nav className="st-episode-nav" aria-label="앨범 메뉴">
        <button type="button" className="st-pill-back" onClick={onBack}><ArrowLeft aria-hidden="true" /> 앨범으로</button>
        <button type="button" className="st-pill-back" onClick={onRoom}>내 방으로</button>
      </nav>
      {episode.isPending && <p role="status">그 주 기록을 펼치고 있어요.</p>}
      {notFound(episode.error) ? (
        <p role="alert">이 액자를 찾지 못했어요. 앨범에서 다시 골라 주세요.</p>
      ) : (
        <ErrorNotice error={episode.error} retry={() => void episode.refetch()} />
      )}
      {e && (
        <>
          <header className="st-episode-head">
            <div className="st-episode-frame">
              <FrameArt item={{ themeId: e.themeId, title: e.title, imageUrl }} />
            </div>
            <div className="st-episode-title">
              <span className="st-episode-badge">{weekLabel(e.weekStart)} · 기념 액자</span>
              <h1>{e.title || '이름 없는 테마'}</h1>
              <p>그 주 문제 다섯 개를 모두 마무리해서 {day(e.awardedAt)}에 받은 액자예요.</p>
              <section className="st-episode-ending" aria-label="그 주 이야기의 끝" data-seen={e.ending.seen || undefined}>
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
            </div>
          </header>
          <section className="st-episode-week" aria-labelledby="episode-missions-h">
            <h2 id="episode-missions-h">그 주 문제</h2>
            <ol className="st-episode-missions" aria-label="그 주 문제">
              {e.missions.map((m) => (
                <li key={m.day} style={{ '--st-hue': m.thinkingType ? thinkingHue[m.thinkingType] : '#7a8c88' } as CSSProperties}>
                  <MissionTile child={child} missionId={m.missionId} day={DAY_LABELS[m.day]} />
                  <span className="st-episode-kind">
                    <i aria-hidden="true" />
                    <span className="st-day">{DAY_LABELS[m.day]}</span>
                    {m.thinkingType && <small>· {studentThinkingLabels[m.thinkingType]}</small>}
                  </span>
                  <strong>{m.title || '문제'}</strong>
                  {m.attemptId ? (
                    <button type="button" className="st-pill-link" onClick={() => onAttempt(m.attemptId!)}>그때 기록 보기</button>
                  ) : (
                    <span className="st-meta">남은 기록이 없어요</span>
                  )}
                </li>
              ))}
            </ol>
          </section>
          {/* 추억 그림책 (docs/proposals/memory-book.md, 미도입 시험 구현) */}
          <MemoryBookPanel child={child} themeId={e.themeId} weekStart={e.weekStart} />
        </>
      )}
    </main>
  )
}
