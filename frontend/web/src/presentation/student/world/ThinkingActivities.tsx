import { useState } from 'react'
import { displayPeriods, useThinkingActivities } from '../../../data/classroom/useClassroom.ts'
import type { Child, Period, ThinkingType } from '../../../domain/classroom.ts'
import { shortRange, thinkingLabels } from '../../../domain/classroom.ts'
import type { ThinkingActivity } from '../../../domain/learning.ts'
import { THINKING_ORDER, thinkingHue } from '../../../domain/studentLook.ts'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'

const { recentPeriod, previousWeek } = displayPeriods

function Items({ items, showType = true }: { items: ThinkingActivity[]; showType?: boolean }) {
  return (
    <ul className="st-activities">
      {items.map((i) => (
        <li key={i.attemptId} className="st-activity">
          {showType && (
            <p className="st-kicker">
              <i style={{ background: thinkingHue[i.thinkingType] }} aria-hidden="true" />
              {thinkingLabels[i.thinkingType]}
            </p>
          )}
          <h3>{i.missionTitle}</h3>
          {i.reflection ? (
            <p>
              돌아보기 · {i.reflection.difficulty}
              {i.reflection.text && <span className="st-activity-note">{i.reflection.text}</span>}
            </p>
          ) : (
            <p className="st-meta">아직 돌아보기를 쓰지 않았어요.</p>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * 생각 활동 (FN-DSH-04): 기간 안에 해 본 미션의 생각 유형과 내가 쓴 돌아보기.
 * 숫자 레벨·등급·순위·점수는 보여 주지 않는다. type을 주면 그 섬(생각 유형)만 모은다.
 */
export function ThinkingActivityList({ child, period, type }: { child: Child; period: Period; type?: ThinkingType }) {
  const query = useThinkingActivities(child, period)
  const items = (query.data?.items ?? []).filter((i) => !type || i.thinkingType === type)
  if (query.isPending)
    return (
      <p className="st-meta" role="status">
        생각 활동을 가져오는 중이에요.
      </p>
    )
  if (query.error)
    return (
      <ErrorNotice
        error={query.error}
        retry={() => {
          void query.refetch()
        }}
      />
    )
  if (query.data.state === 'PROCESSING' || query.data.state === 'FAILED') return <QueryStateNotice state={query.data.state} />
  if (!items.length)
    return (
      <p className="st-empty">
        {type ? `이 기간에 ‘${thinkingLabels[type]}’ 미션은 아직 해 보지 않았어요.` : '이 기간에 해 본 미션이 아직 없어요.'}
      </p>
    )
  return <Items items={items} showType={!type} />
}

/** 학생 메뉴의 "생각 활동" 화면. 기간을 고르고 생각 유형별로 모아 본다. */
export function ThinkingActivitiesPage({ child }: { child: Child }) {
  const [period, setPeriod] = useState<Period>(recentPeriod)
  const query = useThinkingActivities(child, period)
  const items = query.data?.items ?? []
  const types = THINKING_ORDER.filter((type) => items.some((i) => i.thinkingType === type))
  return (
    <main className="st-paper st-sheet">
      <div className="st-sheet-head">
        <div>
          <h1>내 생각 활동</h1>
        </div>
        <label className="st-select">
          기간
          <select
            aria-label="생각 활동 기간"
            value={period.from}
            onChange={(e) => setPeriod(e.target.value === recentPeriod.from ? recentPeriod : previousWeek)}
          >
            <option value={recentPeriod.from}>최근 7일 · {shortRange(recentPeriod)}</option>
            <option value={previousWeek.from}>지난주 · {shortRange(previousWeek)}</option>
          </select>
        </label>
      </div>
      {query.isSuccess && types.length > 0 ? (
        types.map((type) => (
          <section key={type} className="st-activity-group" aria-labelledby={`activity-${type}`}>
            <h2 id={`activity-${type}`}>{thinkingLabels[type]}</h2>
            <Items items={items.filter((i) => i.thinkingType === type)} showType={false} />
          </section>
        ))
      ) : (
        <ThinkingActivityList child={child} period={period} />
      )}
    </main>
  )
}
