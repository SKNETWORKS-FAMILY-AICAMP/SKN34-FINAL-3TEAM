import { useEffect, useMemo, useRef, useState } from 'react'
import { ReportProblem } from '../service/ReportProblem.tsx'
import { ReportExplanations } from './ReportExplanations.tsx'
import type { Child } from '../../domain/classroom.ts'
import type { DailyProblem, ReportPeriodType, ThemeSummary } from '../../domain/parent.ts'
import { reportPeriodType } from '../../domain/parent.ts'
import type { ReportContext, ReportHighlight } from '../../domain/reportHighlight.ts'
import { emptyReportTargets, reportTargets } from '../../domain/reportHighlight.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { knownEntitlement, useChildEntitlement } from '../../data/payment/queries.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { QueryFeedback, MetricCards } from '../common/Workspace.tsx'
import { QueryStateNotice } from '../common/QueryStateNotice.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { EvidenceQuery } from './ParentConversation.tsx'
export function ParentReports({
  child,
  onAskReport, preview, highlight, revealToken = 0, onReportChange,
}: {
  child: Child
  preview?: ReportContext
  highlight?: ReportHighlight | null
  revealToken?: number
  onReportChange?: () => void
  onAskReport: (report: ReportContext) => void
}) {
  const [status, setStatus] = useState(''),
    [kind, setKind] = useState<ReportPeriodType | ''>(''),
    [id, setId] = useState<string | null>(null),
    [revision, setRevision] = useState<number | undefined>(),
    list = useParentQuery(['reports', child.id, status, kind], (signal) =>
      parentApi.reports(child.id, status, signal, kind || undefined), !preview,
    )
  const selected = preview ?? highlight
  const activeId = selected?.reportId ?? id
  const activeRevision = selected?.revision ?? revision
  return (
    <>
      {!preview && <>
      <header className="parent-page-head"><h2>리포트</h2>
      <p>
        하루·한 주의 학습을 자동으로 정리한 결과입니다. 궁금한 점은 AI 챗봇에서 질문할 수 있습니다.
      </p>
      <p>일일 리포트는 매일 자정에 그날 기록으로, 주간 리포트는 일요일 자정에 한 주 기록으로 만들어집니다.</p></header>
      <div className="parent-report-filters"><label>
        리포트 종류{' '}
        <select aria-label="리포트 종류" value={kind} onChange={(e) => setKind(e.target.value as ReportPeriodType | '')}>
          <option value="">전체</option>
          <option value="DAILY">일일</option>
          <option value="WEEKLY">주간</option>
        </select>
      </label>{' '}
      <label>
        생성 상태{' '}
        <select aria-label="리포트 상태" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">전체</option>
          {[
            ['RUNNING', '생성 중'],
            ['COMPLETED', '완료'],
            ['FAILED', '생성 실패'],
          ].map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      </div>
      <QueryFeedback query={list} />
      {list.data && !list.error && (
        <div className="ws-metrics">
          {!list.data.items.length && <p>아직 생성된 리포트가 없습니다.</p>}
          {list.data.items.map((r) => (
            <article className="ws-card" key={r.reportId}>
              <p className="ws-tag">{reportPeriodType(r) === 'DAILY' ? '일일 리포트' : '주간 리포트'}</p>
              <h2>{reportPeriodType(r) === 'DAILY' ? r.period.from : `${r.period.from} ~ ${r.period.to}`}</h2>
              <p>
                {r.status === 'COMPLETED'
                  ? '생성 완료'
                  : r.status === 'FAILED'
                    ? '생성 실패'
                    : '생성 중'}
              </p>
              <QueryStateNotice state={r.state} />
              <button
                className="cj-secondary"
                onClick={() => {
                  onReportChange?.(); setId(r.reportId)
                  setRevision(undefined)
                }}
              >
                리포트 상세 보기
              </button>
            </article>
          ))}
        </div>
      )}
      </>}
      {activeId && (
        <ReportDetail
          key={activeId}
          child={child}
          id={activeId}
          revision={activeRevision}
          compact={!!preview} highlight={highlight} revealToken={revealToken}
          onRevision={value => { setId(activeId); setRevision(value); onReportChange?.() }}
          onAskReport={value => { setId(value.reportId); setRevision(value.revision); onAskReport(value) }}
        />
      )}
    </>
  )
}
function ReportDetail({
  child,
  id,
  revision,
  onRevision,
  onAskReport, compact = false, highlight, revealToken = 0,
}: {
  child: Child
  compact?: boolean
  highlight?: ReportHighlight | null
  revealToken?: number
  id: string
  revision: number | undefined
  onRevision: (v: number | undefined) => void
  onAskReport: (report: ReportContext) => void
}) {
  const q = useParentQuery(
      ['report', child.id, id, revision ?? 'latest'],
      (signal) => parentApi.report(id, child.id, revision, signal),
      true,
      true,
    ),
    regenerate = useParentMutation(() => parentApi.regenerate(id)),
    // 이용권은 entitlement로만 판단한다(#602). 조회 전·실패면 서버가 내려준 리포트 내용을 그대로 쓴다.
    entitlement = knownEntitlement(useChildEntitlement(child.id)),
    conversationOff = entitlement?.conversationEnabled === false,
    download = useParentMutation((format: 'pdf' | 'md') => parentApi.download(id, format)),
    [proof, setProof] = useState<string | null>(null),
    [notice, setNotice] = useState('')
  const r = q.error ? undefined : q.data,
    ready = r?.status === 'COMPLETED',
    daily = !!r && reportPeriodType(r) === 'DAILY'
  const panel = useRef<HTMLElement>(null), lastReveal = useRef(0)
  const targets = useMemo(() => r ? reportTargets(r, highlight) : emptyReportTargets(), [r, highlight])
  const matched = Object.values(targets).reduce((total, values) => total + values.length, 0)
  useEffect(() => {
    if (!highlight || !ready || !matched) return
    const first = panel.current?.querySelector<HTMLElement>('[data-answer-highlight="true"]')
    if (!first) return
    const pane = compact ? panel.current?.closest<HTMLElement>('.parent-insights-report-body') : null
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
    if (pane && window.matchMedia('(min-width:1101px)').matches) {
      pane.scrollTo({ top: pane.scrollTop + first.getBoundingClientRect().top - pane.getBoundingClientRect().top - 16, behavior })
    } else if (revealToken > lastReveal.current) first.scrollIntoView({ block: 'center', behavior })
    if (revealToken > lastReveal.current) first.focus({ preventScroll: true })
    lastReveal.current = revealToken
  }, [highlight, ready, matched, targets, revealToken, compact])
  async function file(format: 'pdf' | 'md') {
    try {
      const data = await download.mutateAsync(format)
      const url = new URL(data.url, location.href)
      if (!['http:', 'https:'].includes(url.protocol))
        throw new Error('허용되지 않은 다운로드 주소입니다.')
      if (Date.parse(data.expiresAt) <= Date.now())
        throw new Error('다운로드 주소가 만료되었습니다.')
      window.location.assign(url.href)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '파일을 받지 못했습니다.')
    }
  }
  return (
    <section className="ws-card report-detail" ref={panel}>
      <h2>{daily ? '일일 리포트 상세' : '리포트 상세'}</h2>
      <ReportProblem targetType="REPORT" targetId={id}/>
      <QueryFeedback query={q} />
      {!compact && r && ready && r.parentSharingEnabled !== false && (
        <div className="parent-report-question"><h3>이 리포트에서 이어서 질문하기</h3>
          <p>{conversationOff ? 'AI 질문은 프리미엄 기능입니다. 리포트의 수치는 계속 확인할 수 있습니다.' : '리포트의 자녀와 기간을 AI 챗봇에 연결합니다.'}</p>
          <button className="cj-primary" disabled={conversationOff} onClick={() => onAskReport({ reportId: r.reportId, revision: r.revision, period: r.period, periodType: daily ? 'DAILY' : 'WEEKLY' })}>이 리포트로 질문하기</button>
        </div>
      )}
      {highlight && r && <><p>선택한 질문 · {highlight.question}</p><p role="status" className="report-highlight-summary">{matched
        ? `선택한 답변과 연결된 ${matched}개 항목을 초록 테두리로 표시했습니다.`
        : '이 답변과 직접 연결된 항목이 현재 리포트 판에는 없습니다.'}</p></>}
      {r && (
        <>
          <p>
            실제 리포트 기간 · {r.period.from} ~ {r.period.to} · {r.revision}판
          </p>
          {r.correctionNotice && (
            <p role="note">이 리포트에 쓰인 판정 중 일부가 리포트를 만든 뒤 정정되었습니다. 리포트 내용은 만들어진 때 그대로입니다.</p>
          )}
          {!compact && <label>
            리포트 판{' '}
            <select
              aria-label="리포트 판"
              value={revision ?? 'latest'}
              onChange={(e) =>
                onRevision(e.target.value === 'latest' ? undefined : Number(e.target.value))
              }
            >
              <option value="latest">최신판</option>
              {r.revisions.map((v) => (
                <option key={v.revision} value={v.revision}>
                  {v.revision}판
                </option>
              ))}
            </select>
          </label>}
          {!ready ? (
            <p role="status">
              {r.status === 'FAILED'
                ? '리포트 생성에 실패했습니다. 기록 없음과는 다릅니다.'
                : '리포트를 생성하고 있습니다. 완료 전 내용을 표시하지 않습니다.'}
            </p>
          ) : (
            <>
              <p>{r.inclusionRule}</p>
              <QueryStateNotice state={r.state} />
              {daily ? (
                <DailyProblems highlighted={targets.problems} problems={r.problems ?? []} canReadOriginals={r.parentSharingEnabled !== false} onProof={setProof} />
              ) : r.narrative ? (
                <>
                  <p>{r.narrative.text}</p>
                  <p>요약 출처 · {r.narrative.source}</p>
                </>
              ) : (
                <p>{r.parentSharingEnabled === false ? '아이의 답변 원문이 비공개여서 서술과 인용을 표시하지 않습니다. 학습 수치는 아래에서 확인할 수 있습니다.' : '수치 리포트입니다. 이 자녀의 플랜에는 서술 요약이 포함되지 않습니다.'}</p>
              )}
              <MetricCards metrics={r.metrics} highlighted={targets.metrics} />
              <ReportExplanations report={r} narrativeEnabled={entitlement?.narrativeEnabled} />
              <div className="ws-actions">
                {r.metrics.map((m, i) => (
                  <button
                    className="cj-secondary"
                    key={i}
                    disabled={r.parentSharingEnabled === false}
                    onClick={() => setProof(m.itemId ?? `metric-${i}`)}
                  >
                    {m.label} 근거
                  </button>
                ))}
              </div>
              {!daily && r.themeSummary && <ThemeSummaryView summary={r.themeSummary} />}
              {!daily && entitlement?.narrativeEnabled !== false && r.parentSharingEnabled !== false && (
                <>
                  <h3>생각 유형별 활동</h3>
                  {r.thinkingTypes.map((t, i) => (
                    <p className="report-highlight-target" data-answer-highlight={targets.thinking.includes(i) ? 'true' : undefined} tabIndex={-1} key={t.type}>
                      <HighlightLabel active={targets.thinking.includes(i)} />
                      {thinkingLabels[t.type]} ·{' '}
                      {t.state === 'NO_RECORD'
                        ? '미관찰 · 확인된 기록 없음'
                        : (t.summary ?? `${t.missions.length}개 미션`)}
                    </p>
                  ))}
                  <h3>되묻기 전후</h3>
                  {!r.changes.length && <p>비교할 답변 쌍이 없습니다.</p>}
                  {r.changes.map((c, i) => (
                    <article className="ws-card report-highlight-target" data-answer-highlight={targets.changes.includes(i) ? 'true' : undefined} tabIndex={-1} key={c.attemptId}>
                      <HighlightLabel active={targets.changes.includes(i)} />
                      {c.followup !== null && <p>받은 질문 · {c.followup}</p>}
                      <div className="ws-grid">
                        <div>
                          <h4>최초 답변</h4>
                          <blockquote>{c.first.text}</blockquote>
                        </div>
                        <div>
                          <h4>추가 답변</h4>
                          <blockquote>{c.revised.text}</blockquote>
                        </div>
                      </div>
                      <p>
                        글자 수 {c.counts.chars.join(' → ')} · 문장 수{' '}
                        {c.counts.sentences.join(' → ')} · 까닭 연결어 수{' '}
                        {c.counts.reasonConnectives.join(' → ')}
                      </p>
                      <small>실제로 센 글의 변화이며 사고력 향상으로 단정하지 않습니다.</small>
                      <button
                        className="cj-secondary"
                        onClick={() => setProof(c.itemId ?? c.attemptId)}
                      >
                        전후 변화 근거
                      </button>
                    </article>
                  ))}
                  <h3>돌아보기</h3>
                  {r.reflections.map((f, i) => (
                    <p className="report-highlight-target" data-answer-highlight={targets.reflections.includes(i) ? 'true' : undefined} tabIndex={-1} key={i}>
                      <HighlightLabel active={targets.reflections.includes(i)} />
                      {f.written ? `${f.difficulty} · ${f.text || '달라진 점 미작성'}` : '미작성'}
                    </p>
                  ))}
                  <h3>아이의 말</h3>
                  {r.quotes.map((v, i) => v.verified && <blockquote className="report-highlight-target" data-answer-highlight={targets.quotes.includes(i) ? 'true' : undefined} tabIndex={-1} key={v.answerId}>
                    <HighlightLabel active={targets.quotes.includes(i)} />{v.text}
                  </blockquote>)}
                  {r.eveningQuestion && (
                    <>
                      <h3>이번 주 저녁 질문</h3>
                      <p>{r.eveningQuestion}</p>
                    </>
                  )}
                </>
              )}
              {!compact && <p>{r.parentSharingEnabled === false ? '원문 비공개 중에는 기존 파일을 제공하지 않습니다. 위 학습 수치는 계속 확인할 수 있습니다.' : '다운로드는 서버가 제공하는 최신판 파일입니다.'}</p>}

            </>
          )}
          {!compact && <div className="parent-report-regenerate"><div className="parent-report-toolbar">{ready && <>                <button
                  className="cj-secondary"
                  disabled={download.isPending || r.parentSharingEnabled === false}
                  onClick={() => {
                    void file('pdf')
                  }}
                >
                  PDF 다운로드
                </button>
                <button
                  className="cj-secondary"
                  disabled={download.isPending || r.parentSharingEnabled === false}
                  onClick={() => {
                    void file('md')
                  }}
                >
                  Markdown 다운로드
                </button>
              </>}<button
            className="cj-secondary"
            disabled={regenerate.isPending || r.status === 'RUNNING' || r.status === 'QUEUED'}
            onClick={() => {
              void regenerate
                .mutateAsync(undefined)
                .then(() => {
                  onRevision(undefined)
                  setNotice('새 판 생성을 요청했습니다. 기존 판은 유지됩니다.')
                })
                .catch(() => {})
            }}
          >
            새 판으로 재생성
          </button></div>
          <p>학부모 재생성은 리포트당 한 번입니다. 이전 판은 유지됩니다.</p></div>}
        </>
      )}
      {r && ready && r.parentSharingEnabled === false && <p role="note">원문 비공개 중에는 원문 근거·AI 질문·파일 다운로드를 이용할 수 없습니다. 위 학습 수치는 계속 확인할 수 있습니다.</p>}
      {notice && <p role="status">{notice}</p>}
      <ErrorNotice error={regenerate.error} />
      <ErrorNotice error={download.error} />
      {proof && r && (
        <Modal title="리포트 항목 근거" onClose={() => setProof(null)}>
          <EvidenceQuery
            queryKey={['report-evidence', child.id, id, proof]}
            load={(signal) => parentApi.reportEvidence(id, proof, signal)}
          />
        </Modal>
      )}
    </section>
  )
}

const judgmentLabels: Record<NonNullable<DailyProblem['judgment']>, string> = {
  CORRECT: '맞게 썼어요',
  PARTIAL: '일부 확인',
  RETHINK: '다시 생각해 보기',
  HELD: '판정 보류',
}
const contextLabels: Record<NonNullable<DailyProblem['context']>, string> = {
  THEME_DAY: '주간 테마 오늘 문제',
  THEME_REVIEW: '되돌아보기 다시 풀기',
  EXTRA: '추가 문제',
}

/** 일일 리포트(P24): 그날 문제별 기록만 보여 준다. 서술·저녁 질문은 없다. */
function DailyProblems({ problems, onProof, canReadOriginals, highlighted }: { problems: DailyProblem[]; canReadOriginals: boolean; onProof: (itemId: string) => void; highlighted: number[] }) {
  if (!problems.length) return <p>이날은 기록이 없습니다.</p>
  return (
    <>
      <h3>그날 푼 문제</h3>
      {problems.map((p, i) => (
        <article className="ws-card report-highlight-target" data-answer-highlight={highlighted.includes(i) ? 'true' : undefined} tabIndex={-1} key={`${p.missionId}-${p.attemptId ?? i}`}>
          <HighlightLabel active={highlighted.includes(i)} />
          <h4>{p.title}</h4>
          <p>
            {p.context ? `${contextLabels[p.context]} · ` : ''}
            {p.judgment ? `판정 ${judgmentLabels[p.judgment]}` : '판정 없음'}
          </p>
          {p.followups.map((f, j) => (
            <div key={j}>
              <p>되묻기 {j + 1} · {f.question}</p>
              <blockquote>{canReadOriginals ? f.answer ?? '보완 답변 없음' : '아이가 답변 원문을 비공개로 두었어요.'}</blockquote>
            </div>
          ))}
          {p.finalAnswer && (
            <>
              <h5>마지막 답</h5>
              <blockquote>{p.finalAnswer}</blockquote>
            </>
          )}
          {p.elements.length > 0 && (
            <p>
              확인된 생각 요소 · {p.elements.filter((e) => e.satisfied).map((e) => e.label).join(', ') || '없음'}
            </p>
          )}
          <p>
            돌아보기 ·{' '}
            {p.reflection?.written ? `${p.reflection.difficulty ?? ''} ${p.reflection.text ?? ''}`.trim() : '쓰지 않음'}
          </p>
          {p.attemptId && canReadOriginals && (
            <button className="cj-secondary" onClick={() => onProof(p.attemptId!)}>
              원문 근거
            </button>
          )}
        </article>
      ))}
      <small>판정 결과는 그날 기록이며 능력 점수가 아닙니다.</small>
    </>
  )
}

/** 주간 리포트의 테마 요약(FN-RPT-17). */
function ThemeSummaryView({ summary }: { summary: ThemeSummary }) {
  return (
    <>
      <h3>이번 주 테마</h3>
      {summary.state === 'NO_RECORD' || !summary.title ? (
        <p>이번 주에는 주간 테마에 참여한 기록이 없습니다.</p>
      ) : (
        <>
          <p>
            {summary.title} · {summary.completed ? '완주' : '진행'}
          </p>
          <ul>
            {summary.days.map((d) => (
              <li key={d.day}>
                {({ MON: '월', TUE: '화', WED: '수', THU: '목', FRI: '금' } as Record<string, string>)[d.day] ?? d.day} ·{' '}
                {d.title ?? '문제'} · {d.completed ? '마침' : '마치지 않음'}
              </li>
            ))}
          </ul>
          {summary.reviewRetries.length > 0 && <p>주말 다시 풀기 {summary.reviewRetries.length}개</p>}
        </>
      )}
    </>
  )
}

function HighlightLabel({ active }: { active: boolean }) {
  return active ? <span className="report-highlight-label">선택한 답변의 근거</span> : null
}
