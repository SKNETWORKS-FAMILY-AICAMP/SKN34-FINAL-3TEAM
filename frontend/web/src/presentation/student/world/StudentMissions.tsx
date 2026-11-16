import { useState } from 'react'
import { displayPeriods, useMissions } from '../../../data/classroom/useClassroom.ts'
import { ThinkingActivityList } from './ThinkingActivities.tsx'
import type { Child, Mission, ThinkingType } from '../../../domain/classroom.ts'
import { studentThinkingLabels } from '../../../domain/classroom.ts'
import { THINKING_ORDER, thinkingHue } from '../../../domain/studentLook.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { SceneArt } from '../MissionScene.tsx'
import { useLook } from './lookContext.ts'

const statusLabel = (m: Mission) =>
  m.status === 'COMPLETED' ? '끝냈어요' : m.status === 'IN_PROGRESS' ? '하는 중' : '시작 전'

/** 미션 고르기 (FN-LRN-01). 생각 유형 칩으로 걸러 볼 수 있다(홈 "더 풀어 보기"로 들어옴, #648). */
export function StudentMissions({
  child,
  type,
  onType,
  onOpen,
}: {
  child: Child
  type: ThinkingType | null
  onType: (type: ThinkingType | null) => void
  onOpen: (mission: Mission) => void
}) {
  const { t } = useLook()
  const missions = useMissions(child)
  const [subject, setSubject] = useState('all')
  const subjects = [...new Set((missions.data ?? []).map((m) => m.subject))]
  const rows = (missions.data ?? []).filter(
    (m) => (!type || m.thinkingType === type) && (subject === 'all' || m.subject === subject),
  )
  return (
    <main className="st-paper st-sheet st-missions-page">
      <div className="st-sheet-head">
        <div>
          <h1 className="st-title-mix"><span>미션 </span>고르기</h1>
          <p>
            {type
              ? `‘${studentThinkingLabels[type]}’ ${t.place}의 미션이에요.`
              : '하고 싶은 미션을 하나 골라요.'}
          </p>
        </div>
        <label className="st-select">
          과목
          <select aria-label="과목 필터" value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="all">모든 과목</option>
            {subjects.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="st-chips" role="group" aria-label="생각 유형">
        <button type="button" aria-pressed={!type} onClick={() => onType(null)}>
          전체
        </button>
        {THINKING_ORDER.map((ty) => (
          <button type="button" key={ty} aria-pressed={type === ty} onClick={() => onType(ty)}>
            <i style={{ background: thinkingHue[ty] }} aria-hidden="true" />
            {studentThinkingLabels[ty]}
          </button>
        ))}
      </div>
      {missions.isPending && (
        <p className="st-meta" role="status">
          미션을 가져오는 중이에요.
        </p>
      )}
      <ErrorNotice
        error={missions.error}
        retry={() => {
          void missions.refetch()
        }}
      />
      {missions.isSuccess && rows.length === 0 && (
        <p className="st-empty">여기에는 아직 고를 수 있는 미션이 없어요. 다른 생각 유형을 골라 볼까요?</p>
      )}
      <div className="st-cards">
        {rows.map((m) => (
          <article className="st-card" key={m.id} data-status={m.status ?? 'NOT_STARTED'}>
            <figure className="st-photo">
              {/* 미션 장면 그림이 있으면 그 그림(안내 화면과 같은 그림), 없으면 기본 장면 그림 */}
              {/^(https?:\/\/|\/[^/])/.test(m.staticSceneUri || m.sceneUri || '') ? (
                <img src={m.staticSceneUri || m.sceneUri} alt="" />
              ) : (
                <SceneArt mission={m} decorative />
              )}
            </figure>
            <p className="st-kicker">
              {m.subject} · {studentThinkingLabels[m.thinkingType]}
            </p>
            <h2>{m.title}</h2>
            <p className="st-question">{m.question}</p>
            <div className="st-card-foot">
              <span className="st-status">{statusLabel(m)}</span>
              <button type="button" className="st-button st-primary" data-open-mission={m.id} onClick={() => onOpen(m)}>
                미션 열기
              </button>
            </div>
          </article>
        ))}
      </div>
      {type && (
        <section className="st-island-activities" aria-labelledby="island-activities-h">
          <h2 id="island-activities-h">최근 7일 이 {t.place}에서 해 본 생각</h2>
          <ThinkingActivityList child={child} period={displayPeriods.recentPeriod} type={type} />
        </section>
      )}
    </main>
  )
}
