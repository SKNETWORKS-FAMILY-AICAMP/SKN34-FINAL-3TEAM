import { useState } from 'react'
import { useMissions } from '../../../data/classroom/useClassroom.ts'
import type { Child, Mission, ThinkingType } from '../../../domain/classroom.ts'
import { thinkingLabels } from '../../../domain/classroom.ts'
import { THINKING_ORDER, thinkingHue } from '../../../domain/studentLook.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { SceneArt } from '../MissionScene.tsx'
import { useLook } from './lookContext.ts'

const statusLabel = (m: Mission) =>
  m.status === 'COMPLETED' ? '끝냈어요' : m.status === 'IN_PROGRESS' ? '하는 중' : '시작 전'

/** 미션 고르기 (FN-LRN-01). 생각 지도에서 고른 곳(유형)으로 바로 걸러 볼 수 있다. */
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
    <main className="st-paper st-sheet">
      <div className="st-sheet-head">
        <div>
          <h1>미션 고르기</h1>
          <p>
            {type
              ? `‘${thinkingLabels[type]}’ ${t.place}의 미션이에요.`
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
            {thinkingLabels[ty]}
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
        <p className="st-empty">여기에는 아직 고를 수 있는 미션이 없어요. 다른 곳을 골라 볼까요?</p>
      )}
      <div className="st-cards">
        {rows.map((m) => (
          <article className="st-card" key={m.id} data-status={m.status ?? 'NOT_STARTED'}>
            <figure className="st-photo">
              <SceneArt mission={m} decorative />
            </figure>
            <p className="st-kicker">
              {m.subject} · {thinkingLabels[m.thinkingType]}
            </p>
            <h2>{m.title}</h2>
            <p className="st-question">{m.question}</p>
            <div className="st-card-foot">
              <span className="st-status">{statusLabel(m)}</span>
              <button type="button" className="st-button st-primary" onClick={() => onOpen(m)}>
                미션 열기
              </button>
            </div>
          </article>
        ))}
      </div>
    </main>
  )
}
