import { correctionImpactText } from '../../domain/admin/operations.ts'
import { useState } from 'react'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
export { ModelRegistry as ModelManager } from './ModelRegistry.tsx'
export function ErrorManager() {
  const q = useAdminQuery(['errors'], (signal) => adminApi.errors(signal)),
    [id, setId] = useState<string | null>(null)
  return (
    <>
      <h2>오류 신고 검토</h2>
      <p>신고와 연결된 시도만 열람할 수 있으며, 열람마다 감사 이력을 남깁니다.</p>
      <QueryFeedback query={q} />
      {q.data &&
        !q.error &&
        q.data.items.map((r) => (
          <article className="ws-card" key={r.reportId}>
            <h3>
              {r.targetType} · {r.status}
            </h3>
            <p>{r.comment}</p>
            <button className="cj-secondary" onClick={() => setId(r.reportId)}>
              신고 상세·연결 기록 열람
            </button>
          </article>
        ))}
      {id && (
        <Modal title="신고 연결 기록 검토" onClose={() => setId(null)}>
          <ErrorDetail id={id} />
        </Modal>
      )}
    </>
  )
}
function ErrorDetail({ id }: { id: string }) {
  const q = useAdminQuery(['error', id], (signal) => adminApi.error(id, signal)),
    [reason, setReason] = useState(''),
    [corrected, setCorrected] = useState('CORRECT'),
    [status, setStatus] = useState('IN_REVIEW'),
    review = useAdminMutation(() => adminApi.reviewError(id, status, reason)),
    correction = useAdminMutation(() => adminApi.correction(id, reason, corrected, id))
  return (
    <>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <p>
            {q.data.category} · {q.data.comment}
          </p>
          <p>접수만으로 판정은 바뀌지 않습니다. 정정 후 원본 답변은 보존합니다.</p>
          {q.data.linkedAttempt?.answers.map((a) => (
            <section key={a.answerId}>
              <h4>신고 연결 답변 v{a.version}</h4>
              <blockquote>{a.text}</blockquote>
              <p>기존 판정 · {a.feedback.judgment?.result ?? a.feedback.status}</p>
            </section>
          ))}
          <form
            className="ws-form"
            onSubmit={(e) => {
              e.preventDefault()
              void review.mutateAsync(undefined).catch(() => {})
            }}
          >
            <label>
              검토 상태
              <select
                aria-label="신고 검토 상태"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                {['RECEIVED', 'IN_REVIEW', 'RESOLVED'].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              검토·정정 사유
              <textarea
                aria-label="검토 사유"
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <button className="cj-secondary" disabled={review.isPending}>
              검토 결과 저장
            </button>
            <ErrorNotice error={review.error} />
          </form>
          <form
            className="ws-form"
            onSubmit={(e) => {
              e.preventDefault()
              void correction.mutateAsync(undefined).catch(() => {})
            }}
          >
            <label>
              정정 결과
              <select aria-label="정정 결과" value={corrected} onChange={(e) => setCorrected(e.target.value)}>
                {['CORRECT', 'PARTIAL', 'RETHINK', 'HELD'].map((value) => <option key={value}>{value}</option>)}
              </select>
            </label>
            <button className="cj-primary" disabled={!reason.trim() || correction.isPending}>
              정정 이력 추가
            </button>
            <ErrorNotice error={correction.error} />
          </form>
          {q.data.corrections.length > 0 && <p>판정 정정과 파생 결과 반영은 별개입니다. 아래 표시는 각 영역에서 확인된 반영 여부입니다.</p>}
          {q.data.corrections.map((c, i) => (
            <section className="ws-card" key={i}>
              <p>
                {c.createdAt} · {c.reason}
              </p>
              <p>{c.corrected}</p>
              <p>{correctionImpactText(c.impact)}</p>
            </section>
          ))}
        </>
      )}
    </>
  )
}
