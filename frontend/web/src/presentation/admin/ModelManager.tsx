import type { CommunityReviewResult, ErrorReport } from '../../domain/admin/operations.ts'
import { answerText, POST_STATUS_LABELS } from '../../domain/retention.ts'
import { correctionImpactText } from '../../domain/admin/operations.ts'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { date, reportStatusLabel } from './adminFormatting.ts'
import { Badge } from './AdminUi.tsx'
import { busyProps } from './busyButton.ts'
export { ModelRegistry as ModelManager } from './ModelRegistry.tsx'
/** 신고 대상 이름. COMMUNITY_POST는 2026-11-06 결정(P20): 접수 즉시 숨김, 처리 결과로 다시 공개 또는 계속 숨김. */
const targetLabels: Record<string, string> = {
  FOLLOWUP: '되묻기 질문',
  JUDGMENT: '판정',
  ANALYSIS: '분석 대화 답변',
  REPORT: '리포트',
  COMMUNITY_POST: '커뮤니티 공유물 · 접수 즉시 숨김',
}
export function ErrorManager() {
  const [params,setParams] = useSearchParams()
  const status=params.get('status') ?? ''
  const [page,setPage] = useState(0)
  const q = useAdminQuery(['errors',status,page], (signal) => adminApi.errors(signal,status,page)),
    [id, setId] = useState<string | null>(null)
  return (
    <>
      <div className="ad-data-toolbar"><h2>오류 신고 검토</h2>
        <label>신고 상태 <select aria-label="신고 상태" value={status} onChange={e=>{
          const next=new URLSearchParams(params)
          if(e.target.value) next.set('status',e.target.value); else next.delete('status')
          setParams(next); setPage(0); setId(null)
        }}><option value="">전체 상태</option>{Object.entries(reportStatusLabel).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      </div>
      <p>신고에 연결된 답변이나 공유물 원문을 열람하면 감사 이력이 남습니다.</p>
      <QueryFeedback query={q} />
      {q.data &&
        !q.error &&
        q.data.items.map((r) => (
          <article className="ws-card" key={r.reportId}>
            <h3 className="ad-report-heading">
              <span>{targetLabels[r.targetType] ?? r.targetType}</span>
              <Badge active={r.status === 'RESOLVED'}>{reportStatusLabel[r.status] ?? r.status}</Badge>
            </h3>
            {r.targetType === 'COMMUNITY_POST' && (
              <p>처리 결과에 따라 다시 공개하거나 계속 숨깁니다. 공유물 원문 열람은 감사 이력에 남습니다.</p>
            )}
            <p>{r.comment}</p>
            <button className="cj-secondary" onClick={() => setId(r.reportId)}>
              신고 상세·연결 기록 열람
            </button>
          </article>
        ))}
      {q.data && !q.error && <div className="ad-list-footer"><span>{q.data.totalElements}건 · {page+1}페이지</span>
        <div><button disabled={page===0} onClick={()=>setPage(page-1)}>이전 신고</button><button disabled={(page+1)*20>=q.data.totalElements} onClick={()=>setPage(page+1)}>다음 신고</button></div></div>}
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
    [status, setStatus] = useState<ErrorReport['status']>('IN_REVIEW'),
    review = useAdminMutation(() => adminApi.reviewError(id, status, reason)),
    correction = useAdminMutation(() => adminApi.correction(id, reason, corrected, id))
  if (q.data?.targetType === 'COMMUNITY_POST' && !q.error) {
    return <CommunityReportDetail report={q.data} refreshing={q.isFetching} />
  }
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
                onChange={(e) => setStatus(e.target.value as ErrorReport['status'])}
              >
                {['RECEIVED', 'IN_REVIEW', 'RESOLVED'].map((v) => (
                  <option key={v} value={v}>{reportStatusLabel[v] ?? v}</option>
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
            <button className="cj-secondary" {...busyProps(review.isPending)}>
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
            <button className="cj-primary" {...busyProps(correction.isPending, !reason.trim())}>
              정정 이력 추가
            </button>
            <ErrorNotice error={correction.error} />
          </form>
          {q.data.corrections.length > 0 && <p>판정 정정과 파생 결과 반영은 별개입니다. 아래 표시는 분석 대화·리포트의 영향 여부와 학습 수치 집계의 반영 여부입니다.</p>}
          {q.data.corrections.map((c, i) => (
            <section className="ws-card" key={i}>
              <time className="ad-cell-note" dateTime={c.createdAt}>{date(c.createdAt)}</time><p>{c.reason}</p>
              <p>{c.corrected}</p>
              <p>{correctionImpactText(c.impact)}</p>
            </section>
          ))}
        </>
      )}
    </>
  )
}

const communityReviewLabels: Record<CommunityReviewResult, string> = {
  REMOVED: '계속 숨김',
  VISIBLE: '다시 공개',
}

function CommunityReportDetail({ report, refreshing }: { report: ErrorReport; refreshing: boolean }) {
  const [reason, setReason] = useState('')
  const [result, setResult] = useState<CommunityReviewResult>('REMOVED')
  const review = useAdminMutation((values: {
    status: ErrorReport['status']
    reason: string
    result?: CommunityReviewResult
  }) => adminApi.reviewError(report.reportId, values.status, values.reason, values.result))

  const saved = report.status === 'RESOLVED' ? report : review.data ?? report
  const resolved = saved.status === 'RESOLVED'
  const completing = saved.status === 'IN_REVIEW'
  const savedResult = saved.reviewResult === 'VISIBLE' || saved.reviewResult === 'REMOVED'
    ? saved.reviewResult
    : undefined
  const post = report.linkedPost
  const original = post?.available ? answerText(post.answer) : ''

  return (
    <>
      <p>{report.comment}</p>
      <section className="ws-card">
        <h4>신고된 공유물 원문</h4>
        {post?.available && <p>현재 공개 상태 · {POST_STATUS_LABELS[post.status] ?? '확인 불가'}</p>}
        {post?.available === false ? <p>파기된 글입니다. 원문을 볼 수 없습니다.</p>
          : original
            ? <blockquote style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{original}</blockquote>
            : <p>원문을 확인할 수 없습니다.</p>}
      </section>
      {resolved ? (
        <section className="ws-form">
          <h4>검토 완료{savedResult && ` · ${communityReviewLabels[savedResult]}`}</h4>
          {saved.reviewReason && <p>검토 사유 · {saved.reviewReason}</p>}
          {savedResult && saved.reviewReason && (
            <button className="cj-secondary" {...busyProps(review.isPending || refreshing)} onClick={() => {
              void review.mutateAsync({
                status: 'RESOLVED',
                reason: saved.reviewReason!,
                result: savedResult,
              }).catch(() => {})
            }}>같은 결과 다시 적용</button>
          )}
        </section>
      ) : (
        <form className="ws-form" onSubmit={(e) => {
          e.preventDefault()
          if (!reason.trim() || review.isPending || refreshing) return
          void review.mutateAsync({
            status: completing ? 'RESOLVED' : 'IN_REVIEW',
            reason,
            result: completing ? result : undefined,
          }).then(() => setReason(''), () => {})
        }}>
          {completing && (
            <label>
              공유물 처리 결과
              <select value={result} onChange={(e) => setResult(e.target.value as CommunityReviewResult)}>
                {Object.entries(communityReviewLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
          )}
          <label>
            검토 사유
            <textarea required value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <button className="cj-primary" {...busyProps(review.isPending || refreshing, !reason.trim())}>
            {completing ? '검토 결과 저장' : '검토 시작'}
          </button>
        </form>
      )}
      {review.isSuccess && <p role="status">검토 내용이 저장되었습니다.</p>}
      <ErrorNotice error={review.error} />
    </>
  )
}
