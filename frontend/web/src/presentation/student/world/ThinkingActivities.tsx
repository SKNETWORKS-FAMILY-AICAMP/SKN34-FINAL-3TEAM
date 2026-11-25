import { useState } from 'react'
import type { CSSProperties } from 'react'
import { displayPeriods, periodName, useThinkingActivities } from '../../../data/classroom/useClassroom.ts'
import type { Child, Period, ThinkingType } from '../../../domain/classroom.ts'
import { shortRange, studentThinkingLabels } from '../../../domain/classroom.ts'
import type { ThinkingActivity } from '../../../domain/learning.ts'
import { THINKING_ORDER, thinkingHue } from '../../../domain/studentLook.ts'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'

const { recentPeriod, previousWeek } = displayPeriods

function Items({ items, showType = true }: { items: ThinkingActivity[]; showType?: boolean }) {
  return (
    <ul className="st-activities">
      {items.map((i) => (
        <li key={i.attemptId} className="st-activity" style={{ '--st-hue': thinkingHue[i.thinkingType] } as CSSProperties}>
          <i className="st-activity-bar" aria-hidden="true" />
          <div className="st-activity-name">
            <h3>{i.missionTitle}</h3>
            {showType && <small>{studentThinkingLabels[i.thinkingType]}</small>}
          </div>
          {i.reflection ? (
            <p className="st-activity-reflect">
              <span className="st-visually-hidden">돌아보기 · </span><b>{i.reflection.difficulty}</b>
              {i.reflection.text && <span className="st-activity-note">{i.reflection.text}</span>}
            </p>
          ) : (
            <p className="st-meta st-activity-reflect">아직 돌아보기를 쓰지 않았어요.</p>
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
        {type
          ? `${periodName(period)} 동안 ‘${studentThinkingLabels[type]}’ 미션은 아직 안 해 봤어요.`
          : `${periodName(period)} 동안 해 본 미션이 아직 없어요. 미션을 하나 풀면 여기에 쌓여요.`}
      </p>
    )
  return <Items items={items} showType={!type} />
}

/**
 * 학생 메뉴의 "생각 활동" 화면(#648 시안 Activities). 위에 생각 유형 다섯 칸 요약(그 기간에 해 본 미션 이름, 숫자 없음),
 * 아래에 해 본 미션과 내 돌아보기(그 칸 안에서만 스크롤). 기간은 예전과 같은 최근 7일·지난주.
 */
export function ThinkingActivitiesPage({ child }: { child: Child }) {
  const [period, setPeriod] = useState<Period>(recentPeriod)
  const query = useThinkingActivities(child, period)
  const items = query.data?.items ?? []
  const periods: [Period, string][] = [[recentPeriod, '최근 7일'], [previousWeek, '지난주']]
  return (
    <main className="st-paper st-sheet st-activities-page">
      <header className="st-page-head">
        <h1 className="st-title-mix"><span>내 </span>생각 활동</h1>
        <div className="st-segment" role="group" aria-label="생각 활동 기간">
          {periods.map(([p, name]) => (
            <button type="button" key={p.from} aria-pressed={period.from === p.from} onClick={() => setPeriod(p)} title={shortRange(p)}>
              {name}<span className="st-visually-hidden"> · {shortRange(p)}</span>
            </button>
          ))}
        </div>
      </header>
      {/* 다섯 칸은 해 본 것을 모아 보는 줄: 해 본 칸만 색과 미션 이름, 안 한 칸은 글 없이 흐린 점선(사용자 결정 2026-11-15 ②).
          하나도 안 했으면 빈 칸 다섯 개 대신 줄을 숨기고 아래 목록 안내 한 줄만 둔다. */}
      {query.isSuccess && items.length > 0 && (
        <section className="st-activity-types-wrap" aria-labelledby="activity-types-h">
          <h2 id="activity-types-h">{periodName(period)} 동안 해 본 생각</h2>
          <div className="st-activity-types">
            {THINKING_ORDER.map((type) => {
              const latest = items.find((i) => i.thinkingType === type)
              return (
                <div key={type} className="st-activity-type" data-done={latest ? true : undefined} style={{ '--st-hue': thinkingHue[type] } as CSSProperties}>
                  <strong><i aria-hidden="true" />{studentThinkingLabels[type]}</strong>
                  {latest ? <span>‘{latest.missionTitle}’에서 해 봤어요</span> : <span className="st-visually-hidden">아직 안 해 봤어요</span>}
                </div>
              )
            })}
          </div>
        </section>
      )}
      <section className="st-activity-list" aria-labelledby="activity-list-h" data-tour="activities-list">
        <h2 id="activity-list-h">해 본 미션과 내 돌아보기</h2>
        <div className="st-scroll">
          <ThinkingActivityList child={child} period={period} />
        </div>
      </section>
    </main>
  )
}
