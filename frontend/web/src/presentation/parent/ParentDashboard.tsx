import { useState } from 'react'
import { useNavigate } from 'react-router'
import { parentApi } from '../../data/parent/api.ts'
import { useParentDashboard, useParentQuery } from '../../data/parent/queries.ts'
import type { Child, Metric, PublicAttempt } from '../../domain/classroom.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import type { Scope } from '../../domain/parent.ts'
import { metricText } from '../../domain/parent.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { Modal } from '../shared/ClassroomParts.tsx'

const shortDate = (iso?: string) => (iso ? iso.slice(5, 10).replace('-', '.') : '-')
const stateText = {
  OK: null,
  NO_RECORD: '기록 없음',
  INSUFFICIENT_SAMPLE: '표본 부족',
  PROCESSING: '처리 중',
  FAILED: '조회 실패',
} as const

/**
 * 학부모 대시보드 (FN-DSH-06~10, 학부모 대시보드 시안).
 * 숫자는 서버 Metric 그대로 쓰고, 표본이 적으면 비율을 만들지 않는다. 기록 없는 유형은 '미관찰'로 둔다.
 */
export function ParentDashboard({ child, scope }: { child: Child; scope: Scope }) {
  const q = useParentDashboard(scope),
    [record, setRecord] = useState<string | null>(null)
  const summary = q.summary.data && !q.summary.error ? q.summary.data : null
  const thinking = q.thinking.data && !q.thinking.error ? q.thinking.data.items : null
  const seen = thinking?.filter((t) => t.state !== 'NO_RECORD').length
  return (
    <div className="pd">
      <header className="pd-head">
        <span className="pd-eyebrow">대시보드 · 공책</span>
        <h1>{child.nickname}의 학습 기록</h1>
        <p className="pd-sub">
          초등 {child.grade}학년
          {summary && ` · 실제 조회 기간 ${summary.period.from} ~ ${summary.period.to} (KST)`}
        </p>
      </header>

      <QueryFeedback query={q.summary} />
      {summary && (
        <div className="pd-status" role="status" data-query-state={summary.state}>
          {summary.state !== 'OK' && <span className="pd-chip pd-chip-warn">{stateText[summary.state]}</span>}
          <span>
            {summary.state === 'NO_RECORD'
              ? '아직 집계할 기록이 없습니다. ‘이 자녀로 학습 시작’에서 첫 활동을 시작해 보세요.'
              : summary.state === 'INSUFFICIENT_SAMPLE'
                ? `이 기간 집계 대상 활동이 ${summary.metrics[0]?.count ?? 0}건입니다. 비율은 5건 이상일 때부터 보여 드립니다.`
                : '기간 내 기록을 집계했습니다.'}
          </span>
          <span className="pd-note">관찰 기록이며 사고력 진단이 아닙니다.</span>
        </div>
      )}

      <section aria-label="기간 요약" className="pd-kpis">
        {summary?.metrics.map((m) => (
          <Kpi key={m.label} m={m} />
        ))}
        <article className="pd-card pd-kpi">
          <h2>관찰된 생각 유형</h2>
          <div className="pd-value">
            <strong>{seen ?? '-'}</strong>
            <span>/ 5가지</span>
          </div>
          {thinking && (
            <div className="pd-bars" aria-hidden="true">
              {thinking.map((t) => (
                <span key={t.type} data-seen={t.state !== 'NO_RECORD' || undefined} />
              ))}
            </div>
          )}
          <p>기간 내 기록이 있는 유형 수 · 유형별 내용은 아래 목록</p>
        </article>
      </section>

      <div className="pd-split">
        <section aria-labelledby="types-h" className="pd-card pd-types">
          <div className="pd-card-head">
            <h2 id="types-h">다섯 가지 생각 활동</h2>
            <span>기록이 없는 유형은 ‘미관찰’로 둡니다</span>
          </div>
          <QueryFeedback query={q.thinking} />
          {thinking && (
            <ul>
              {thinking.map((t) => (
                <li key={t.type}>
                  <span className="pd-type">
                    <i aria-hidden="true" data-seen={t.state !== 'NO_RECORD' || undefined} />
                    {thinkingLabels[t.type]}
                  </span>
                  {t.state === 'NO_RECORD' ? (
                    <span className="pd-chip">미관찰</span>
                  ) : (
                    <span className="pd-chip pd-chip-ok">{t.missions.length}개 미션에서 관찰</span>
                  )}
                  <span className="pd-links">
                    {t.missions.map((m) => (
                      <button type="button" key={m.attemptId} onClick={() => setRecord(m.attemptId)}>
                        {m.title}
                      </button>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <ReportCard child={child} />
      </div>

      <section aria-labelledby="rec-h" className="pd-card">
        <div className="pd-card-head">
          <h2 id="rec-h">학습 기록</h2>
          <span>{summary?.inclusionRule}</span>
        </div>
        <QueryFeedback query={q.records} />
        {q.records.data && !q.records.error && (
          <>
            {!q.records.data.items.length ? (
              <p className="pd-empty">아직 기록이 없습니다. 첫 학습 후 답변이 여기에 연결됩니다.</p>
            ) : (
              <div className="pd-table-wrap">
                <table className="pd-table">
                  <thead>
                    <tr>
                      <th scope="col">날짜</th>
                      <th scope="col">미션</th>
                      <th scope="col">생각 유형</th>
                      <th scope="col">답변</th>
                      <th scope="col">되묻기</th>
                      <th scope="col">돌아보기</th>
                      <th scope="col">상태</th>
                      <th scope="col">
                        <span className="st-visually-hidden">원문</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.records.data.items.map((a) => (
                      <RecordRow key={a.attemptId} a={a} onOpen={() => setRecord(a.attemptId)} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="pd-foot">
              실제 목록 기간 · {q.records.data.period.from} ~ {q.records.data.period.to} · 원문에서
              최초 답변·되묻기·보완 답변·생각 열기 이용·돌아보기를 볼 수 있고, 아이의 생각 메모는
              포함하지 않습니다.
            </p>
          </>
        )}
      </section>
      {record && (
        <Modal title="학습 기록 원문" onClose={() => setRecord(null)}>
          <RecordDetail childId={child.id} id={record} />
        </Modal>
      )}
    </div>
  )
}

function Kpi({ m }: { m: Metric }) {
  const ratio = m.value !== null
  return (
    <article className="pd-card pd-kpi">
      <h2>{m.label}</h2>
      <div className="pd-value">
        {metricText(m) === '확인되지 않음' ? (
          <strong>확인되지 않음</strong>
        ) : ratio ? (
          <>
            <strong>{Math.round(m.value! * 100)}%</strong>
            <span>
              {m.numerator} / {m.denominator}건
            </span>
          </>
        ) : m.numerator !== m.denominator ? (
          <>
            <strong>{m.numerator}</strong>
            <span>/ {m.denominator}건</span>
          </>
        ) : (
          <>
            <strong>{m.count}</strong>
            <span>건</span>
          </>
        )}
      </div>
      <p>{m.formula}</p>
    </article>
  )
}

function RecordRow({ a, onOpen }: { a: PublicAttempt; onOpen: () => void }) {
  const extra = a.answers.length - 1,
    asked = a.answers.some((v) => v.feedback.followup)
  return (
    <tr>
      <td className="pd-num">{shortDate(a.answers[0]?.submittedAt)}</td>
      <td>
        <strong>{a.mission.title}</strong>
        <div className="pd-muted">{a.mission.subject}</div>
      </td>
      <td>{thinkingLabels[a.mission.thinkingType]}</td>
      <td className="pd-num">
        {a.answers.length}개{extra > 0 ? ` (보완 ${extra})` : ''}
      </td>
      <td>{asked ? (extra > 0 ? '받음 · 답함' : '받음') : '없음'}</td>
      <td>{a.reflection ? a.reflection.difficulty : '미작성'}</td>
      <td>
        <span className={a.status === 'COMPLETED' ? 'pd-chip pd-chip-ok' : 'pd-chip'}>
          {a.status === 'COMPLETED' ? '완료' : '진행 중'}
        </span>
      </td>
      <td className="pd-right">
        <button type="button" className="pd-link" aria-label={`${a.mission.title} 원문 보기`} onClick={onOpen}>
          원문 보기
        </button>
      </td>
    </tr>
  )
}

function ReportCard({ child }: { child: Child }) {
  const navigate = useNavigate()
  const list = useParentQuery(['reports', child.id, ''], (signal) => parentApi.reports(child.id, '', signal))
  const latest = list.data && !list.error ? list.data.items[0] : undefined
  const go = (path: string) => navigate(`${path}${window.location.search}`)
  return (
    <section aria-labelledby="report-h" className="pd-card pd-report">
      <h2 id="report-h">주간 리포트</h2>
      <QueryFeedback query={list} />
      {list.data && !list.error && !latest && <p>아직 생성된 리포트가 없습니다. 직전 주 리포트는 월요일 오전 7시에 생성됩니다.</p>}
      {latest && (
        <div className="pd-report-meta">
          <span className="pd-num">
            {latest.period.from} ~ {latest.period.to} · {latest.revision}판
          </span>
          <span className={latest.status === 'COMPLETED' ? 'pd-chip pd-chip-ok' : latest.status === 'FAILED' ? 'pd-chip pd-chip-warn' : 'pd-chip'}>
            {{ QUEUED: '대기', RUNNING: '생성 중', COMPLETED: '생성 완료', FAILED: '생성 실패' }[latest.status]}
          </span>
        </div>
      )}
      <p>
        {child.plan === 'FREE'
          ? '무료 이용권에서는 리포트 수치만 제공합니다. 요약 문장과 근거 인용은 프리미엄에서 볼 수 있습니다.'
          : child.plan === 'PREMIUM' ? '수치와 요약, 근거가 된 답변 인용을 함께 볼 수 있습니다.' : '이용권 정보를 확인하지 못했습니다.'}
      </p>
      <div className="pd-actions">
        <button type="button" className="cj-primary" onClick={() => go('/parent/report')}>
          리포트 열기
        </button>
        <button type="button" className="cj-secondary" onClick={() => go('/parent/analysis')}>
          기록에 물어보기
        </button>
      </div>
    </section>
  )
}

/** 학습 기록 원문: 최초 답변·되묻기·보완 답변·생각 열기 이용·돌아보기 (FN-DSH-09). 메모는 없다. */
export function RecordDetail({ childId, id }: { childId: string; id: string }) {
  const q = useParentQuery(['record', childId, id], (signal) =>
    parentApi.record(childId, id, signal),
  )
  return (
    <>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <h3>{q.data.mission.title}</h3>
          {q.data.answers.map((a) => (
            <section key={a.answerId}>
              <h4>
                {a.version === 1 ? '최초 답변' : `보완 답변 ${a.version - 1}`} · {a.submittedAt}
              </h4>
              <blockquote>{a.text}</blockquote>
              {a.feedback.followup && <p>되묻기 · {a.feedback.followup.question}</p>}
            </section>
          ))}
          <p>생각 열기 이용: {q.data.helped ? '이용함' : '이용 안 함'}</p>
          <h4>돌아보기</h4>
          <p>
            {q.data.reflection
              ? `${q.data.reflection.difficulty} · ${q.data.reflection.text || '달라진 점 미작성'}`
              : '미작성'}
          </p>
        </>
      )}
    </>
  )
}
