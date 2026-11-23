import { useState } from 'react'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import {
  EXPRESSION_REVIEW_LABELS, EXPRESSION_REVIEW_SOURCES, hasNextPage,
} from '../../domain/admin/expressionReview.ts'
import type { ExpressionReview, ExpressionReviewLabel, ExpressionReviewSource } from '../../domain/admin/expressionReview.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge } from './AdminUi.tsx'
import { date } from './adminFormatting.ts'
import './modelRegistry.css'
import { busyProps } from './busyButton.ts'

const SIZE = 20
const LABEL_ORDER: ExpressionReviewLabel[] = ['OFFENSIVE', 'CLEAN', 'SKIP']

/** 표현 검토 라벨링 (FN-ADM-24, #728). 글만 보이고 학생 이름·ID 없음. 열람·라벨은 core가 감사 기록(P07) */
export function ExpressionReviewManager() {
  const [labeled, setLabeled] = useState(false)
  const [source, setSource] = useState<ExpressionReviewSource | ''>('')
  const [page, setPage] = useState(0)
  const [saved, setSaved] = useState('')
  const filter = { labeled, source: source || undefined, page, size: SIZE }
  const q = useAdminQuery(['expression-reviews', filter], signal => adminApi.expressionReviews(filter, signal))
  const items = q.data && !q.error ? q.data.items : null
  return <section className="ws-stack expression-review" aria-label="표현 검토">
    <p>표현 분류 모델이 애매하다고 본 답변과 신고로 숨긴 공유물의 <strong>글만</strong> 보입니다. 학생 이름·ID는 없습니다.
      목록을 볼 때와 라벨을 붙일 때 감사 이력이 남고, 붙인 라벨은 다음 재학습의 정답으로 쓰입니다.</p>
    <div className="ws-actions" role="group" aria-label="표현 검토 보기">
      <button aria-pressed={!labeled} onClick={() => { setLabeled(false); setPage(0) }}>라벨 전</button>
      <button aria-pressed={labeled} onClick={() => { setLabeled(true); setPage(0) }}>라벨 완료</button>
      <label>출처 <select aria-label="출처" value={source} onChange={e => { setSource(e.target.value as ExpressionReviewSource | ''); setPage(0) }}>
        <option value="">전체</option>
        {(Object.keys(EXPRESSION_REVIEW_SOURCES) as ExpressionReviewSource[]).map(s => <option key={s} value={s}>{EXPRESSION_REVIEW_SOURCES[s]}</option>)}
      </select></label>
    </div>
    <QueryFeedback query={q} />
    <p role="status">{saved}</p>
    {items && !items.length && <p role="status">{labeled ? '라벨을 붙인 글이 없습니다.' : '검토할 글이 없습니다.'}</p>}
    {items?.map(item => <ExpressionReviewCard key={`${item.id}:${item.label ?? ''}`} item={item} onSaved={setSaved} />)}
    {q.data && !q.error && (page > 0 || hasNextPage(page, SIZE, q.data.totalElements)) && <nav className="ws-actions" aria-label="표현 검토 쪽">
      <button {...busyProps(q.isFetching, page === 0)} onClick={() => setPage(p => p - 1)}>이전</button>
      <span>{page + 1}쪽 · 전체 {q.data.totalElements}건</span>
      <button {...busyProps(q.isFetching, !hasNextPage(page, SIZE, q.data.totalElements))} onClick={() => setPage(p => p + 1)}>다음</button>
    </nav>}
  </section>
}

/** 저장 안내는 목록 위에 둔다: "라벨 전" 보기에서는 저장 뒤 다시 불러오면 이 카드가 사라진다 */
function ExpressionReviewCard({ item, onSaved }: { item: ExpressionReview; onSaved: (message: string) => void }) {
  const mutation = useAdminMutation((label: ExpressionReviewLabel) => adminApi.labelExpressionReview(item.id, label))
  return <article className="ws-card" aria-label={`${EXPRESSION_REVIEW_SOURCES[item.source]} ${date(item.createdAt)}`}>
    <h3 className="ad-report-heading"><span>{EXPRESSION_REVIEW_SOURCES[item.source]}</span>
      {item.label ? <Badge active={item.label === 'CLEAN'}>{EXPRESSION_REVIEW_LABELS[item.label]}</Badge> : <Badge active={false}>라벨 전</Badge>}</h3>
    <p className="expression-review-text">{item.text}</p>
    <small>모델 {item.modelVersion ?? '기록 없음'} · 들어온 시각 {date(item.createdAt)}{item.labeledAt ? ` · 라벨 ${date(item.labeledAt)}` : ''}</small>
    <div className="ws-actions" role="group" aria-label="라벨 붙이기">
      {LABEL_ORDER.map(label => <button key={label} aria-pressed={item.label === label} {...busyProps(mutation.isPending)}
        onClick={() => { onSaved(''); void mutation.mutateAsync(label).then(() => onSaved(`글 하나를 "${EXPRESSION_REVIEW_LABELS[label]}"(으)로 저장했습니다.`)).catch(() => {}) }}>
        {EXPRESSION_REVIEW_LABELS[label]}</button>)}
    </div>
    <ErrorNotice error={mutation.error} />
  </article>
}
