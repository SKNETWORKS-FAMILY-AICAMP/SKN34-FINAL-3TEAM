import { useState } from 'react'
import { Palette } from 'lucide-react'
import { useStudentHome } from '../../../data/classroom/useClassroom.ts'
import type { Child, Mission, ThinkingType } from '../../../domain/classroom.ts'
import { thinkingLabels } from '../../../domain/classroom.ts'
import { companionLabel, islands, thinkingHue, todayMission } from '../../../domain/studentLook.ts'
import { ErrorNotice, Modal } from '../../shared/ClassroomParts.tsx'
import { Customize } from './Customize.tsx'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { SceneArt } from '../MissionScene.tsx'
import { Companion } from './Companion.tsx'
import { IslandArt, Ride } from './ThemeArt.tsx'
import { useLook } from './lookContext.ts'

/** 받침에 맞춰 을/를을 붙인다 (섬을, 공터를). */
const withObject = (word: string) => {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  return word + (code >= 0 && code % 28 ? '을' : '를')
}
const savedAt = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'short', timeStyle: 'short' })

/**
 * 학생 홈 = 생각 지도 (FN-DSH-01·02, 테마 캔버스 홈).
 * 다섯 생각 유형이 지도 위 한 곳씩이고, 숫자는 홈 응답의 미션 상태로 센 "끝낸 미션 수"뿐이다(레벨·점수 없음).
 */
export function ThinkingMap({
  child,
  onResume,
  onOpen,
  onType,
  onJournal,
}: {
  child: Child
  onResume: (attemptId: string) => void
  onOpen: (mission: Mission) => void
  onType: (type: ThinkingType) => void
  onJournal: () => void
}) {
  const { t, companion } = useLook()
  const [decorating, setDecorating] = useState(false)
  const query = useStudentHome(child),
    home = query.error ? undefined : query.data
  const ready = home && home.state !== 'FAILED' && home.state !== 'PROCESSING'
  const today = home ? todayMission(home) : null
  const places = home ? islands(home) : []
  return (
    <main className="st-home">
      <h1 className="st-visually-hidden">학습 홈 · {t.title}</h1>
      {query.isPending && <QueryStateNotice state="PROCESSING" />}
      <ErrorNotice
        error={query.error}
        retry={() => {
          void query.refetch()
        }}
      />
      {home && home.state !== 'OK' && (
        <div className="st-paper st-notice">
          <QueryStateNotice state={home.state} />
          {!ready && (
            <button type="button" className="st-button" onClick={() => void query.refetch()}>
              다시 확인
            </button>
          )}
        </div>
      )}
      {ready && (
        <div className="st-home-grid">
          <section className="st-today" aria-labelledby="today-h">
            <div className="st-torn st-torn-back" aria-hidden="true" />
            <div className="st-torn st-today-card">
              {home.resume ? (
                <>
                  <p className="st-kicker">
                    이어서 하기 · {thinkingLabels[home.resume.mission.thinkingType]}
                  </p>
                  <h2 id="today-h">{home.resume.mission.title}</h2>
                  <p className="st-meta">
                    {home.resume.draft?.savedAt
                      ? `마지막 저장 ${savedAt(home.resume.draft.savedAt)}`
                      : '아직 저장한 글은 없어요.'}
                  </p>
                  <figure className="st-photo">
                    <SceneArt mission={home.resume.mission} decorative />
                  </figure>
                  <button
                    type="button"
                    className="st-button st-primary"
                    onClick={() => onResume(home.resume!.attemptId)}
                  >
                    이어서 작성하기
                  </button>
                </>
              ) : today ? (
                <>
                  <p className="st-kicker">
                    오늘의 미션 · {thinkingLabels[today.thinkingType]} · 초{child.grade}
                  </p>
                  <h2 id="today-h">{today.title}</h2>
                  <p className="st-meta">{today.subject} · 10분이면 충분해요.</p>
                  <figure className="st-photo">
                    <SceneArt mission={today} decorative />
                  </figure>
                  <button type="button" className="st-button st-primary" onClick={() => onOpen(today)}>
                    시작하기
                  </button>
                </>
              ) : (
                <>
                  <p className="st-kicker">오늘의 미션</p>
                  <h2 id="today-h">지금 고를 수 있는 미션을 다 끝냈어요</h2>
                  <p className="st-meta">내 공책에서 지난 생각을 다시 볼 수 있어요.</p>
                  <button type="button" className="st-button st-primary" onClick={onJournal}>
                    내 공책 보기
                  </button>
                </>
              )}
            </div>
          </section>
          <section className="st-map" aria-labelledby="map-h">
            <h2 id="map-h" className="st-visually-hidden">
              생각 지도
            </h2>
            <svg className="st-map-path" aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none">
              <path
                d="M14 18 C30 4 46 2 58 10 C72 18 86 22 82 40 C78 52 56 52 46 58 C58 70 72 74 82 80"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <ul className="st-islands">
              {places.map((p) => (
                <li key={p.type} data-type={p.type}>
                  <button
                    type="button"
                    className="st-island"
                    data-today={p.today || undefined}
                    onClick={() => onType(p.type)}
                  >
                    <IslandArt t={t} hue={thinkingHue[p.type]} today={p.today} />
                    <span className="st-island-name">
                      <strong>{p.label}</strong>
                      <small>끝낸 미션 {p.done}</small>
                    </span>
                    {p.today && <span className="st-today-flag">오늘 여기!</span>}
                  </button>
                </li>
              ))}
            </ul>
            <div className="st-buddy">
              <div className="st-buddy-figure">
                <Ride id={t.id} />
                <Companion kind={companion} size={104} />
              </div>
              <p className="st-bubble">
                나는 {companionLabel(companion)}!{' '}
                {today
                  ? `오늘은 ‘${thinkingLabels[today.thinkingType]}’ ${t.place}에 가 볼까?`
                  : `가 보고 싶은 ${withObject(t.place)} 눌러 봐.`}
              </p>
            </div>
            <button type="button" className="st-button st-decorate" onClick={() => setDecorating(true)}>
              <Palette aria-hidden="true" />
              꾸미기
            </button>
          </section>
        </div>
      )}
      {decorating && (
        <Modal title="내 생각 지도 꾸미기" onClose={() => setDecorating(false)}>
          <Customize child={child} onDone={() => setDecorating(false)} />
        </Modal>
      )}
    </main>
  )
}
