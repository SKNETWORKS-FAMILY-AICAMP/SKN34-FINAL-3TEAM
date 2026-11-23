import { useEffect, useRef, useState } from 'react'
import { Info, Search, X } from 'lucide-react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { EXPRESSION_REVIEW_LABELS, EXPRESSION_REVIEW_SOURCES, hasNextPage } from '../../domain/admin/expressionReview.ts'
import type { ExpressionReview, ExpressionReviewLabel, ExpressionReviewSource } from '../../domain/admin/expressionReview.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { date } from './adminFormatting.ts'
import { TableScroll } from './AdminUi.tsx'
import { busyProps } from './busyButton.ts'
import './expression-review.css'

const SIZE = 20
const LABEL_ORDER: ExpressionReviewLabel[] = ['OFFENSIVE', 'CLEAN', 'SKIP']
const SOURCES = Object.keys(EXPRESSION_REVIEW_SOURCES) as ExpressionReviewSource[]
const PENDING = '검토 대기'

function titleOf(item: ExpressionReview) {
  const characters = Array.from(item.text.replace(/\s+/g, ' ').trim())
  if (!characters.length) return '작성한 글 없음'
  return characters.slice(0, 46).join('') + (characters.length > 46 ? '…' : '')
}

function Status({ label }: { label: ExpressionReviewLabel | null }) {
  const color = label === 'CLEAN' ? 'good' : label === 'OFFENSIVE' ? 'warn' : label === 'SKIP' ? 'neutral' : 'wait'
  return <span className={'ops-status ' + color}>{label ? EXPRESSION_REVIEW_LABELS[label] : PENDING}</span>
}

/** FN-ADM-24. 검색과 상태 필터는 서버에서 열람한 쪽에만 적용한다. */
export function ExpressionReviewManager() {
  const [params, setParams] = useSearchParams()
  const location = useLocation(), navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState('')
  const opener = useRef<HTMLButtonElement | null>(null)
  const searchField = useRef<HTMLInputElement>(null)
  const labeled = params.get('tab') === 'labels'
  const tabName = labeled ? '라벨 이력' : PENDING
  const source = SOURCES.find(s => s === params.get('source'))
  const status = (labeled ? LABEL_ORDER : ['PENDING']).find(s => s === params.get('status')) ?? ''
  const rawPage = Number(params.get('page'))
  const page = Number.isSafeInteger(rawPage) && rawPage >= 0 ? rawPage : 0
  const reviewId = params.get('reviewId')
  const filter = { labeled, source, page, size: SIZE }
  const query = useAdminQuery(['expression-reviews', filter], signal => adminApi.expressionReviews(filter, signal))
  const data = query.error ? undefined : query.data
  const lastPage = data ? Math.max(0, Math.ceil(data.totalElements / SIZE) - 1) : null
  useEffect(() => {
    if (lastPage === null || page <= lastPage) return
    setParams(before => {
      const next = new URLSearchParams(before)
      if (lastPage) next.set('page', String(lastPage))
      else next.delete('page')
      next.delete('reviewId')
      return next
    }, { replace: true })
  }, [page, lastPage, setParams])

  function changed(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    return next
  }
  function closeDetail() {
    if (location.state?.expressionReviewId === reviewId) void navigate(-1)
    else setParams(changed({ reviewId: null }), { replace: true })
  }
  function restoreFocus() {
    const target = opener.current?.isConnected ? opener.current : searchField.current
    target?.focus({ preventScroll: true })
  }
  const keyword = search.trim().toLocaleLowerCase('ko')
  const rows = data?.items.filter(item => {
    if (status && (item.label ?? 'PENDING') !== status) return false
    if (!keyword) return true
    const searchable = [item.text, EXPRESSION_REVIEW_SOURCES[item.source], item.label ? EXPRESSION_REVIEW_LABELS[item.label] : PENDING,
      item.modelVersion, item.createdAt, date(item.createdAt), item.labeledAt, item.labeledAt && date(item.labeledAt)]
    return searchable.some(value => value?.toLocaleLowerCase('ko').includes(keyword))
  }) ?? []
  const selected = data?.items.find(item => item.id === reviewId)
  const multiPage = !!data && data.totalElements > SIZE
  const locallyFiltered = !!(keyword || status)
  const dateTitle = labeled ? '처리 일시' : '접수 일시'
  return <section className="ops-page expression-review" aria-label="표현 검토">
    <header className="page-intro"><h1>표현 검토</h1><p>검토가 필요한 글의 문맥을 확인하고, 운영자가 분류한 결과를 살펴봅니다.</p></header>
    <div className="ops-notice"><Info size={17} aria-hidden="true"/><span>학생 이름과 ID 없이 검토할 글만 표시합니다. 목록 열람과 라벨 저장은 감사 이력에 기록됩니다.</span></div>
    <nav className="ops-tabs" aria-label="표현 검토 보기">{(['pending', 'labels'] as const).map(tab =>
      <Link key={tab} to={{ search: changed({ tab, page: null, status: null, reviewId: null }).toString() }}
        aria-current={(tab === 'labels') === labeled ? 'page' : undefined} onClick={() => { setSearch(''); setNotice('') }}>
        {tab === 'labels' ? '라벨 이력' : PENDING}</Link>)}</nav>
    <section className="panel ops-records" aria-labelledby="ops-list-title">
      <header><div className="ops-records-heading"><h2 id="ops-list-title">{tabName}</h2>
        {data && <span className="total" aria-live="polite">{locallyFiltered && multiPage ? '현재 쪽 ' : ''}{locallyFiltered ? rows.length : data.totalElements}건</span>}</div>
        <div className="ops-tools"><label className="ops-search"><Search size={16} aria-hidden="true"/><input type="search" ref={searchField}
          aria-label="목록 검색" placeholder="목록 검색" value={search} onChange={event => setSearch(event.target.value)}/></label>
          <label className="filter-choice"><select aria-label="상태 필터" value={status} onChange={event => setParams(changed({ status: event.target.value, reviewId: null }), { replace: true })}>
            <option value="">전체 상태</option>{labeled ? LABEL_ORDER.map(label => <option value={label} key={label}>{EXPRESSION_REVIEW_LABELS[label]}</option>) :
              <option value="PENDING">{PENDING}</option>}</select></label>
          <label className="filter-choice"><select aria-label="출처" value={source ?? ''} onChange={event => setParams(changed({ source: event.target.value, page: null, reviewId: null }), { replace: true })}>
            <option value="">전체 출처</option>{SOURCES.map(s => <option value={s} key={s}>{EXPRESSION_REVIEW_SOURCES[s]}</option>)}</select></label>
        </div></header>
      {multiPage && <p className="ops-filter-scope">현재 페이지에서 검색과 상태 필터를 적용합니다.</p>}
      <QueryFeedback query={query}/>
      <div className="ops-rows">{rows.length > 0 && <TableScroll label={tabName + ' 표'}><table className="ops-table" aria-label={tabName}>
        <thead><tr>{['검토 항목', '접수 경로', dateTitle, '상태'].map(col => <th key={col} scope="col">{col}</th>)}</tr></thead>
        <tbody>{rows.map(item => <tr key={item.id}><th scope="row">
          <button type="button" className="ops-open-row" aria-label={titleOf(item) + ' 상세 보기'} onClick={event => {
            opener.current = event.currentTarget
            setNotice('')
            setParams(changed({ reviewId: item.id }), { state: { expressionReviewId: item.id } })
          }}>{titleOf(item)}</button></th>
          <td data-label="접수 경로">{EXPRESSION_REVIEW_SOURCES[item.source]}</td>
          <td data-label={dateTitle}>{date(labeled ? item.labeledAt : item.createdAt)}</td>
          <td data-label="상태"><Status label={item.label}/></td></tr>)}</tbody></table></TableScroll>}
        {data && !rows.length && <div className="ops-empty"><strong>{locallyFiltered || source ? '조건에 맞는 기록이 없습니다.' : labeled ? '라벨을 붙인 글이 없습니다.' : '검토할 글이 없습니다.'}</strong>
          {(locallyFiltered || source) && <button type="button" onClick={() => {
            setSearch(''); setParams(changed({ status: null, source: null, page: null, reviewId: null }), { replace: true })
            searchField.current?.focus()
          }}>검색 조건 지우기</button>}</div>}
      </div>
      {data && (page > 0 || multiPage) && <nav className="ops-pagination" aria-label="표현 검토 쪽">
        <button {...busyProps(query.isFetching, !page)} onClick={() => setParams(changed({ page: String(page - 1), reviewId: null }))}>이전</button>
        <span>{page + 1} / {(lastPage ?? 0) + 1}</span>
        <button {...busyProps(query.isFetching, !hasNextPage(page, SIZE, data.totalElements))} onClick={() => setParams(changed({ page: String(page + 1), reviewId: null }))}>다음</button></nav>}
    </section>
    {notice && <p role="status">{notice}</p>}
    {selected && <ReviewDetail key={selected.id} item={selected} close={closeDetail} restoreFocus={restoreFocus} saved={label => {
      if (!labeled || (status && status !== label)) opener.current = null
      setNotice('라벨을 저장했습니다. · ' + EXPRESSION_REVIEW_LABELS[label]); closeDetail()
    }}/>}
    {reviewId && data && !selected && <div role="status">이 페이지에서 해당 검토 항목을 찾을 수 없습니다. <button onClick={closeDetail}>목록으로</button></div>}
  </section>
}

function ReviewDetail({ item, close, saved, restoreFocus }: {
  item: ExpressionReview; close: () => void; saved: (label: ExpressionReviewLabel) => void; restoreFocus: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const lock = useRef(false), mounted = useRef(false)
  const focusList = useRef(restoreFocus)
  const mutation = useAdminMutation((label: ExpressionReviewLabel) => adminApi.labelExpressionReview(item.id, label))
  useEffect(() => {
    const node = dialog.current!
    const returnFocus = focusList.current
    node.showModal()
    mounted.current = true
    return () => { mounted.current = false; node.close(); returnFocus() }
  }, [])
  function save(label: ExpressionReviewLabel) {
    if (lock.current) return
    lock.current = true
    void mutation.mutateAsync(label).then(() => { if (mounted.current) saved(label) })
      .catch(() => {}).finally(() => { lock.current = false })
  }
  return <dialog className="ops-detail" aria-labelledby="ops-detail-title" ref={dialog}
    onCancel={event => { event.preventDefault(); if (!lock.current) close() }}>
    <header><div><Status label={item.label}/><h2 id="ops-detail-title">{titleOf(item)}</h2></div>
      <button type="button" className="ops-dismiss" aria-label="상세 닫기" {...busyProps(mutation.isPending)} onClick={close}><X size={20} aria-hidden="true"/></button></header>
    <dl className="ops-fields">
      <div><dt>접수 경로</dt><dd>{EXPRESSION_REVIEW_SOURCES[item.source]}</dd></div>
      <div><dt>접수 일시</dt><dd>{date(item.createdAt)}</dd></div>
      {item.label && <div><dt>처리 일시</dt><dd>{date(item.labeledAt)}</dd></div>}
      <div><dt>검토 글</dt><dd className="expression-review-text">{item.text || '작성한 글 없음'}</dd></div>
      {item.modelVersion && <div><dt>모델 버전</dt><dd>{item.modelVersion}</dd></div>}
    </dl>
    <div className="expression-label-actions" role="group" aria-label="라벨 붙이기">{LABEL_ORDER.map(label =>
      <button type="button" key={label} aria-pressed={item.label === label} {...busyProps(mutation.isPending)} onClick={() => save(label)}>{EXPRESSION_REVIEW_LABELS[label]}</button>)}</div>
    <ErrorNotice error={mutation.error}/>
    <footer><small>막을 글·정상 라벨은 재학습에 사용됩니다.</small><button type="button" className="btn ghost" {...busyProps(mutation.isPending)} onClick={close}>닫기</button></footer>
  </dialog>
}
