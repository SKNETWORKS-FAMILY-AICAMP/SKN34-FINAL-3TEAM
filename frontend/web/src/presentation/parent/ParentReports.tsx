import { useState } from 'react'
import type { Child, Period } from '../../domain/classroom.ts'
import type { Scope } from '../../domain/parent.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { QueryFeedback, MetricCards } from '../common/Workspace.tsx'
import { QueryStateNotice } from '../common/QueryStateNotice.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { EvidenceQuery } from './ParentConversation.tsx'
export function ParentReports({
  child,
  scope,
  onAnalysis,
}: {
  child: Child
  scope: Scope
  onAnalysis: (p: Period) => void
}) {
  const [status, setStatus] = useState(''),
    [id, setId] = useState<string | null>(null),
    [revision, setRevision] = useState<number | undefined>(),
    list = useParentQuery(['reports', child.id, status], (signal) =>
      parentApi.reports(child.id, status, signal),
    )
  return (
    <>
      <h1>주간 리포트</h1>
      <p>
        화면 공통 선택 기간 {scope.from} ~ {scope.to} · 주간 리포트는 KST 월~일 기준이므로 실제
        리포트 기간을 따로 표시합니다.
      </p>
      <p>직전 주 리포트는 월요일 오전 7시에 생성됩니다.</p>
      <label>
        생성 상태{' '}
        <select aria-label="리포트 상태" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">전체</option>
          {[
            ['QUEUED', '대기'],
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
      <QueryFeedback query={list} />
      {list.data && !list.error && (
        <div className="ws-metrics">
          {!list.data.items.length && <p>아직 생성된 리포트가 없습니다.</p>}
          {list.data.items.map((r) => (
            <article className="ws-card" key={r.reportId}>
              <h2>
                {r.period.from} ~ {r.period.to}
              </h2>
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
                  setId(r.reportId)
                  setRevision(undefined)
                }}
              >
                리포트 상세 보기
              </button>
            </article>
          ))}
        </div>
      )}
      {id && (
        <ReportDetail
          key={id}
          child={child}
          id={id}
          revision={revision}
          onRevision={setRevision}
          onAnalysis={onAnalysis}
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
  onAnalysis,
}: {
  child: Child
  id: string
  revision: number | undefined
  onRevision: (v: number | undefined) => void
  onAnalysis: (p: Period) => void
}) {
  const q = useParentQuery(
      ['report', child.id, id, revision ?? 'latest'],
      (signal) => parentApi.report(id, child.id, revision, signal),
      true,
      true,
    ),
    regenerate = useParentMutation(() => parentApi.regenerate(id)),
    download = useParentMutation((format: 'pdf' | 'md') => parentApi.download(id, format)),
    [proof, setProof] = useState<string | null>(null),
    [notice, setNotice] = useState('')
  const r = q.error ? undefined : q.data,
    ready = r?.status === 'COMPLETED'
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
    <section className="ws-card">
      <h2>리포트 상세</h2>
      <QueryFeedback query={q} />
      {r && (
        <>
          <p>
            실제 리포트 기간 · {r.period.from} ~ {r.period.to} · {r.revision}판
          </p>
          <label>
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
          </label>
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
              {r.narrative ? (
                <>
                  <p>{r.narrative.text}</p>
                  <p>요약 출처 · {r.narrative.source}</p>
                </>
              ) : (
                <p>수치 리포트입니다. 이 자녀의 플랜에는 서술 요약이 포함되지 않습니다.</p>
              )}
              <MetricCards metrics={r.metrics} />
              <div className="ws-actions">
                {r.metrics.map((m, i) => (
                  <button
                    className="cj-secondary"
                    key={i}
                    onClick={() => setProof(m.itemId ?? `metric-${i}`)}
                  >
                    {m.label} 근거
                  </button>
                ))}
              </div>
              {child.plan === 'PREMIUM' && (
                <>
                  <h3>생각 유형별 활동</h3>
                  {r.thinkingTypes.map((t) => (
                    <p key={t.type}>
                      {thinkingLabels[t.type]} ·{' '}
                      {t.state === 'NO_RECORD'
                        ? '미관찰 · 확인된 기록 없음'
                        : (t.summary ?? `${t.missions.length}개 미션`)}
                    </p>
                  ))}
                  <h3>되묻기 전후</h3>
                  {!r.changes.length && <p>비교할 답변 쌍이 없습니다.</p>}
                  {r.changes.map((c) => (
                    <article className="ws-card" key={c.attemptId}>
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
                    <p key={i}>
                      {f.written ? `${f.difficulty} · ${f.text || '달라진 점 미작성'}` : '미작성'}
                    </p>
                  ))}
                  <h3>아이의 말</h3>
                  {r.quotes
                    .filter((v) => v.verified)
                    .map((v) => (
                      <blockquote key={v.answerId}>{v.text}</blockquote>
                    ))}
                  {r.eveningQuestion && (
                    <>
                      <h3>이번 주 저녁 질문</h3>
                      <p>{r.eveningQuestion}</p>
                    </>
                  )}
                </>
              )}
              <p>다운로드는 서버가 제공하는 최신판 파일입니다.</p>
              <div className="ws-actions">
                <button className="cj-secondary" onClick={() => onAnalysis(r.period)}>
                  이 기간의 기록에 질문
                </button>
                <button
                  className="cj-secondary"
                  disabled={download.isPending}
                  onClick={() => {
                    void file('pdf')
                  }}
                >
                  PDF 다운로드
                </button>
                <button
                  className="cj-secondary"
                  disabled={download.isPending}
                  onClick={() => {
                    void file('md')
                  }}
                >
                  Markdown 다운로드
                </button>
              </div>
            </>
          )}
          <button
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
          </button>
          <p>학부모 재생성은 리포트당 한 번입니다. 이전 판은 유지됩니다.</p>
        </>
      )}
      <p role="status">{notice}</p>
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
