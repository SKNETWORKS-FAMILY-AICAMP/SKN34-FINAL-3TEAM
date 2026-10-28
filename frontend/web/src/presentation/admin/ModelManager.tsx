import { correctionImpactText } from '../../domain/admin/operations.ts'
import { useState } from 'react'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
export function ModelManager() {
  const q = useAdminQuery(['models'], (signal) => adminApi.models(signal)),
    [name, setName] = useState('judge'),
    [version, setVersion] = useState(''),
    [kind, setKind] = useState('PROMPT'),
    [evaluation, setEvaluation] = useState(''),
    [approver, setApprover] = useState(''),
    [reason, setReason] = useState(''),
    register = useAdminMutation(() =>
      adminApi.registerModel({ name, version, kind, evalResult: evaluation, approvedBy: approver }),
    ),
    action = useAdminMutation((v: { id: string; action: 'activate' | 'rollback' }) =>
      adminApi.modelAction(v.id, v.action, reason),
    ),
    [notice, setNotice] = useState('')
  return (
    <>
      <h2>모델·프롬프트 버전</h2>
      <p>
        실제 평가·승인 시스템 연동 전 목업입니다. 활성화·되돌리기는 새 이력이며 기존 결과를 덮어쓰지
        않습니다.
      </p>
      <QueryFeedback query={q} />
      <label>
        변경 사유
        <input
          aria-label="버전 변경 사유"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      {q.data && !q.error && (
        <div className="ws-metrics">
          {q.data.items.map((v) => (
            <article className="ws-card" key={v.id}>
              <h3>
                {v.name}@{v.version}
              </h3>
              <p>
                {v.kind} · {v.status} · 승인자 {v.approvedBy ?? '미승인'}
              </p>
              <p>평가 근거 · {v.evalResult ?? '없음'}</p>
              <div className="ws-actions">
                <button
                  className="cj-secondary"
                  disabled={!reason.trim() || action.isPending || v.status === 'ACTIVE'}
                  onClick={() => {
                    void action
                      .mutateAsync({ id: v.id, action: 'activate' })
                      .then(() =>
                        setNotice('서버에서 활성화를 확인했습니다. 기존 결과는 유지됩니다.'),
                      )
                      .catch(() => {})
                  }}
                >
                  활성화
                </button>
                <button
                  className="cj-secondary"
                  disabled={!reason.trim() || action.isPending || v.status !== 'INACTIVE'}
                  onClick={() => {
                    void action
                      .mutateAsync({ id: v.id, action: 'rollback' })
                      .then(() =>
                        setNotice('이전 승인 버전으로 되돌렸습니다. 재분석은 요청하지 않았습니다.'),
                      )
                      .catch(() => {})
                  }}
                >
                  이 버전으로 되돌리기
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      <p role="status">{notice}</p>
      <ErrorNotice error={action.error} />
      <section className="ws-card">
        <h3>새 버전 등록</h3>
        <form
          className="ws-form"
          onSubmit={(e) => {
            e.preventDefault()
            void register
              .mutateAsync(undefined)
              .then(() => setNotice('평가 근거와 함께 버전을 등록했습니다.'))
              .catch(() => {})
          }}
        >
          <label>
            종류
            <select aria-label="버전 종류" value={kind} onChange={(e) => setKind(e.target.value)}>
              {['RUBRIC', 'MODEL', 'PROMPT', 'GENERATION'].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            이름
            <input
              aria-label="모델 이름"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            버전
            <input
              aria-label="모델 버전"
              required
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            />
          </label>
          <label>
            평가 근거
            <textarea
              aria-label="평가 근거"
              required
              value={evaluation}
              onChange={(e) => setEvaluation(e.target.value)}
            />
          </label>
          <label>
            승인자
            <input
              aria-label="승인자"
              required
              value={approver}
              onChange={(e) => setApprover(e.target.value)}
            />
          </label>
          <button className="cj-primary" disabled={register.isPending}>
            버전 등록
          </button>
          <ErrorNotice error={register.error} />
        </form>
      </section>
    </>
  )
}
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
