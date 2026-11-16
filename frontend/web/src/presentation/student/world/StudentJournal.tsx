import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowLeft } from 'lucide-react'
import { displayPeriods, periodName, useLearningActions, useRecords } from '../../../data/classroom/useClassroom.ts'
import type { Answer, Child, Period, PublicAttempt } from '../../../domain/classroom.ts'
import { shortRange, studentThinkingLabels } from '../../../domain/classroom.ts'
import { comparisonAnswerText } from '../../../domain/learning.ts'
import type { LearningMission } from '../../../domain/learning.ts'
import { thinkingHue } from '../../../domain/studentLook.ts'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { difficultyLabel, feedbackHeadline, followupLabel } from './missionSteps.ts'

const { recentPeriod, previousWeek, thisWeek } = displayPeriods
const DAYS = ['일', '월', '화', '수', '목', '금', '토']
const day = (iso: string) => new Date(iso.slice(0, 10) + 'T00:00:00Z')
const label = (iso: string) => { const d = day(iso); return `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 ${DAYS[d.getUTCDay()]}` }
/** 그 날이 든 주의 월요일(YYYY-MM-DD) */
const mondayOf = (iso: string) => { const d = day(iso); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return d.toISOString().slice(0, 10) }
const sunday = (monday: string) => { const d = day(monday); d.setUTCDate(d.getUTCDate() + 6); return d.toISOString().slice(0, 10) }
const weekName = (monday: string) => {
  if (monday === thisWeek.from) return '이번 주'
  if (monday === previousWeek.from) return '지난주'
  const d = day(monday)
  return `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 주`
}
const lastAt = (r: PublicAttempt) => r.answers.at(-1)?.submittedAt ?? r.finishedAt ?? ''
const statusOf = (r: PublicAttempt) => (r.status === 'COMPLETED' ? '마무리' : r.finishedAt ? '돌아보기 대기' : '하는 중')

/**
 * 내 공책(/student/journal, SC-02-013, #648 시안 Journal). 내가 쓴 답을 주별로 묶어 한 줄씩 보여 준다.
 * 조회는 예전과 같은 기록 훅(useRecords)과 기간 선택이고, 줄을 누르면 기록 상세, 오른쪽 버튼은 이어 하기·결과 다시 보기.
 * 과목 선택·줄의 과목 표시는 뺐다(팀 결정 기능명세 P15 "집중 과목은 국어 우선"(2026-11-01, #213)이라 거를 것이 없음, 사용자 결정 2026-11-16).
 */
export function StudentJournal({ child, onDetail, onContinue, onMissions }: {
  child: Child
  onDetail: (record: PublicAttempt) => void
  onContinue: (attemptId: string) => void
  onMissions: () => void
}) {
  const [period, setPeriod] = useState<Period>(recentPeriod)
  const records = useRecords(child, 'STUDENT', period)
  const rows = records.data ?? []
  const weeks: { monday: string; rows: PublicAttempt[] }[] = []
  for (const r of [...rows].sort((a, b) => lastAt(b).localeCompare(lastAt(a)))) {
    const monday = lastAt(r) ? mondayOf(lastAt(r)) : ''
    const week = weeks.find((w) => w.monday === monday)
    if (week) week.rows.push(r)
    else weeks.push({ monday, rows: [r] })
  }
  return (
    <main className="st-paper st-sheet st-journal-page">
      <header className="st-page-head">
        <div>
          <h1 className="st-title-mix"><span>내 </span>공책</h1>
          <p>내가 쓴 답과 돌아보기가 모두 남아 있어요.</p>
        </div>
        <div className="cj-filters">
          <select aria-label="공책 기간" value={period.from}
            onChange={(e) => setPeriod(e.target.value === recentPeriod.from ? recentPeriod : previousWeek)}>
            <option value={recentPeriod.from}>최근 7일 · {shortRange(recentPeriod)}</option>
            <option value={previousWeek.from}>지난주 · {shortRange(previousWeek)}</option>
          </select>
        </div>
      </header>
      <div className="st-scroll st-journal-weeks">
        {records.isPending && <QueryStateNotice state="PROCESSING">기록을 읽는 중입니다.</QueryStateNotice>}
        <ErrorNotice error={records.error} retry={() => void records.refetch()} />
        {records.isSuccess && rows.length === 0 && (
          <QueryStateNotice state="NO_RECORD">
            {periodName(period)} 동안 쓴 답이 없어요.
            <button type="button" className="cj-primary" onClick={onMissions}>
              미션 고르기
            </button>
          </QueryStateNotice>
        )}
        {weeks.map((w) => (
          <section key={w.monday} className="st-journal-week" aria-labelledby={`journal-${w.monday}`}>
            <h2 id={`journal-${w.monday}`}>{w.monday ? weekName(w.monday) : '날짜 없음'}{w.monday && <small> · {shortRange({ from: w.monday, to: sunday(w.monday) })}</small>}</h2>
            <ul className="st-journal-rows">
              {w.rows.map((r) => (
                <li key={r.attemptId} className="st-journal-row" style={{ '--st-hue': thinkingHue[r.mission.thinkingType] } as CSSProperties}>
                  <button type="button" className="st-journal-open" onClick={() => onDetail(r)}>
                    <i aria-hidden="true" />
                    <span className="st-journal-date">{lastAt(r) ? label(lastAt(r)) : ''}</span>
                    <span className="st-journal-title">
                      <strong>{r.mission.title}</strong>
                      <small>{studentThinkingLabels[r.mission.thinkingType]}</small>
                    </span>
                    <span className="st-journal-status" data-done={r.status === 'COMPLETED' || undefined}>{statusOf(r)}</span>
                  </button>
                  <button type="button" className="st-pill-link" onClick={() => onContinue(r.attemptId)}>
                    {r.finishedAt ? '결과 다시 보기' : '이어서 하기'}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </main>
  )
}

/** 학생이 읽는 날짜(예 "10월 26일", 한국 시간) */
const readableDay = (iso: string) => new Date(iso).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric' })
const str = (v: unknown) => (typeof v === 'string' ? v : '')

/**
 * 답 한 버전의 내용. 풀이 단계는 단계 목록과 최종 답, 논술은 칸 이름(미션 입력 틀)과 함께,
 * 그 밖(서술·고르기·순서·분류, 원본 칸이 없는 답)은 이전 답 비교와 같은 표시 함수(comparisonAnswerText)로 보인다.
 */
function AnswerBody({ answer, mission }: { answer: Answer; mission: LearningMission }) {
  const content = (answer.content ?? {}) as unknown as Record<string, unknown>
  if (answer.inputType === 'SOLUTION_STEPS' && Array.isArray(content.steps)) {
    const final = str(content.finalAnswer).trim()
    return (
      <>
        <ol className="st-jd-steps" aria-label="풀이 단계">
          {content.steps.map((step, i) => (
            <li key={i} data-empty={!str(step).trim() || undefined}>{str(step).trim() || '(비움)'}</li>
          ))}
        </ol>
        {final && <p className="st-jd-final"><b>최종 답</b> {final}{mission.answerUnit ? ` ${mission.answerUnit}` : ''}</p>}
      </>
    )
  }
  const essay = content.essay as { claim?: unknown; reasons?: unknown; rebuttal?: unknown } | undefined
  if (answer.inputType === 'ESSAY' && essay && typeof essay === 'object') {
    const reasons = Array.isArray(essay.reasons) ? essay.reasons : []
    const rows: [string, string][] = [
      [mission.inputTemplate?.[0] || '내 주장', str(essay.claim)],
      [mission.inputTemplate?.[1] || '이유 1', str(reasons[0])],
      [mission.inputTemplate?.[2] || '이유 2', str(reasons[1])],
      [mission.inputTemplate?.[3] || '다른 의견에 답하기', str(essay.rebuttal)],
    ]
    return (
      <dl className="st-jd-essay">
        {rows.filter(([, v]) => v.trim()).map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>
    )
  }
  return (
    <p className="st-jd-text">
      {comparisonAnswerText({ answerId: answer.answerId, version: answer.version, text: answer.text, content }, mission)}
    </p>
  )
}

/**
 * 내 공책 기록 상세(#648 시안 JournalDetail, 사용자 의견 2026-11-16 "공책에서 기록 보는 화면도 이상해").
 * 목록에서 고른 기록(useRecords 응답 그대로)만 쓰고 조회 요청을 새로 만들지 않는다. 머리는 미션 장면(있으면)·꼬리표·섞은 제목·질문,
 * 가운데는 답 버전 카드(그 답 뒤 되묻기는 카드 안 하늘색 칸, 마지막 카드는 굵은 테두리), 아래는 돌아보기와
 * 다시 풀기(마무리한 기록만, 문제 푸는 화면의 '이 미션 다시 풀기'와 같은 시작 요청). 생각 메모는 기록 조회에 없고 넣지 않는다.
 * 기록 응답(core DashboardPublicAttempt)에 시작 맥락(context)이 없어 시안 꼬리표의 "테마 문제"는 보이지 않는다.
 * PC에서도 칸 안 스크롤 없이 학생 틀 전체가 아래로 내려간다(.st-fit 아님).
 */
export function StudentJournalEntry({ record, child, onBack, onWork }: {
  record: PublicAttempt
  child: Child
  onBack: () => void
  onWork: (attemptId: string) => void
}) {
  const title = useRef<HTMLHeadingElement>(null)
  const learning = useLearningActions()
  useEffect(() => {
    title.current?.focus({ preventScroll: true })
    title.current?.closest('.st-stage')?.scrollTo?.({ top: 0 })
  }, [record.attemptId])
  const mission = record.mission as LearningMission
  const scene = mission.staticSceneUri || mission.sceneUri
  const at = lastAt(record)
  const words = mission.title.trim().split(/\s+/)
  const head = words.length > 1 ? words.slice(0, -1).join(' ') + ' ' : ''
  const tail = words.at(-1) ?? ''
  async function restart() {
    try {
      const next = await learning.start.mutateAsync({ mission: record.mission, child })
      onWork(next.attemptId)
    } catch {
      /* 실패는 아래 ErrorNotice가 보인다 */
    }
  }
  return (
    <main className="st-paper st-sheet st-jd-page" style={{ '--st-hue': thinkingHue[mission.thinkingType] } as CSSProperties}>
      <button type="button" className="st-pill-back" onClick={onBack}><ArrowLeft aria-hidden="true" /> 내 공책</button>
      <header className="st-jd-head">
        {scene && /^(https?:\/\/|\/[^/])/.test(scene) && <img className="st-jd-scene" src={scene} alt="" />}
        <div className="st-jd-title">
          <span className="st-jd-tag">
            {studentThinkingLabels[mission.thinkingType]}{at ? ` · ${readableDay(at)}` : ''}
          </span>
          <h1 ref={title} tabIndex={-1} className="st-title-mix">
            {head}{head ? <span>{tail}</span> : tail}
          </h1>
          <p className="st-jd-question">{mission.question}</p>
        </div>
      </header>
      <section className="st-jd-answers" aria-label="내 답 기록">
        {record.answers.length === 0 && <p className="st-jd-empty">아직 보낸 답이 없어요.</p>}
        {record.answers.map((a, i) => {
          const name = a.version === 1 ? '처음 남긴 답' : `덧붙인 답 ${a.version - 1}`
          const f = a.feedback
          const result = f.status === 'DONE' ? f.judgment?.result : undefined
          // 되묻기가 붙은 "한 번 더" 결과는 하늘색 되묻기 칸이 대신 말한다(시안: 첫 카드엔 되묻기만, 마지막 카드엔 결과)
          const verdict = !(f.followup && f.status === 'DONE' && result !== 'CORRECT' && result !== 'HELD')
          return (
            <article key={a.answerId} className="st-jd-version" data-last={i === record.answers.length - 1 || undefined} aria-label={name}>
              <small className="st-jd-version-name">{name} · 별도 버전 보존</small>
              <AnswerBody answer={a} mission={mission} />
              {f.followup && (
                <div className="st-jd-asked">
                  <small>{followupLabel(f.followup.type)}</small>
                  <p>{f.followup.question}</p>
                </div>
              )}
              {verdict && (
                <p className="st-jd-verdict" data-correct={result === 'CORRECT' || undefined}>
                  <span>{feedbackHeadline(f).replace(/\.$/, '')}</span>
                  {f.judgment?.trial && <small>AI 채점(시범)</small>}
                </p>
              )}
            </article>
          )
        })}
      </section>
      <section className="st-jd-foot" aria-label="돌아보기와 다시 풀기">
        <div className="st-jd-reflect">
          <h2>돌아보기</h2>
          {record.reflection ? (
            <>
              <p><b>이번 활동</b> {difficultyLabel(record.reflection.difficulty)}</p>
              <p><b>달라진 점</b> {record.reflection.text.trim() || '따로 적지 않았어요.'}</p>
            </>
          ) : (
            <p>아직 돌아보기를 남기지 않았어요.</p>
          )}
        </div>
        {record.status === 'COMPLETED' && (
          <div className="st-jd-retry">
            <h2>다시 풀어 보기</h2>
            <p>다시 풀면 이번 답과 나란히 비교해 볼 수 있어요. 이번 답은 공책에 그대로 남아요.</p>
            <button type="button" className="st-pill-link" disabled={learning.start.isPending} onClick={() => void restart()}>
              다시 풀기
            </button>
            <ErrorNotice error={learning.start.error} />
          </div>
        )}
      </section>
    </main>
  )
}
