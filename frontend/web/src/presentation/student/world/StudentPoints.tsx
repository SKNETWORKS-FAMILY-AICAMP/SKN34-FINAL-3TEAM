import { useEffect, useRef, useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { useMyPoints } from '../../../data/retention/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { POINT_EVENT_LABELS, POINT_RULES } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import './retention.css'

// 연도는 네 자리(예: 2026. 11. 26. 오후 3:05, #1093). dateStyle 'short'는 연도를 두 자리(26.)로 줄인다
const when = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' })

/**
 * 내 포인트 (/student/points, P21, API 명세 2.10, #648 시안 Points). 잔액은 나와 학부모님만 보고, 순위·소멸은 없다.
 * 왼쪽 잔액·쌓는 법, 오른쪽 내역(그 칸 안에서만 스크롤). 꾸미기 해금은 꾸미기 화면으로 간다.
 */
export function StudentPoints({ child, onSettings, onCustomize }: { child: Child; onSettings: () => void; onCustomize: () => void }) {
  const [page, setPage] = useState(0)
  const points = useMyPoints(child.id, page)
  const title = useRef<HTMLHeadingElement>(null)
  // 설정의 "내 포인트 보기"·옛 주소로 들어오면 제목에 초점(#583 동작 유지)
  useEffect(() => { title.current?.focus() }, [])
  const data = points.error ? undefined : points.data
  return (
    <main className="st-paper st-sheet st-points-page">
      <section className="st-points-left" aria-labelledby="points-h">
        <button type="button" className="st-pill-back" onClick={onSettings}><ArrowLeft aria-hidden="true" /> 설정</button>
        <h1 id="points-h" ref={title} tabIndex={-1} className="st-title-mix"><span>내 </span>포인트</h1>
        {points.isPending && <p role="status">포인트를 확인하고 있어요.</p>}
        <ErrorNotice error={points.error} retry={() => void points.refetch()} />
        {data && (
          <p className="st-balance">
            지금 <strong>{data.balance}</strong>포인트
          </p>
        )}
        <button type="button" className="st-button st-primary" onClick={onCustomize}>
          꾸미기 해금하러 가기
        </button>
        <h2>포인트는 이렇게 쌓여요</h2>
        <ul className="st-rules">
          {POINT_RULES.map((r) => (
            <li key={r.type}>
              <b>+{r.amount}</b>
              <span><b>{POINT_EVENT_LABELS[r.type]}</b><small>{r.note}</small></span>
            </li>
          ))}
        </ul>
      </section>
      <section className="st-points-right" aria-labelledby="ledger-h">
        <h2 id="ledger-h">쌓이고 쓴 내역</h2>
        {data && (data.items.length === 0 ? (
          <p className="st-meta">아직 내역이 없어요.</p>
        ) : (
          <ul className="st-ledger">
            {data.items.map((e, i) => (
              <li key={`${e.createdAt}-${i}`}>
                <span><b>{POINT_EVENT_LABELS[e.eventType]}</b><small>{when(e.createdAt)}</small></span>
                <strong data-minus={e.amount < 0 || undefined}>
                  {e.amount > 0 ? `+${e.amount}` : e.amount}
                </strong>
              </li>
            ))}
          </ul>
        ))}
        {data && data.totalElements > data.size && <nav className="st-points-pages" aria-label="포인트 내역 페이지">
          <button type="button" className="st-button" disabled={page === 0 || points.isFetching} onClick={() => setPage(p => p - 1)}>이전 내역</button>
          <span>{page + 1} / {Math.ceil(data.totalElements / data.size)}쪽</span>
          <button type="button" className="st-button" disabled={(page + 1) * data.size >= data.totalElements || points.isFetching}
            onClick={() => setPage(p => p + 1)}>다음 내역</button>
        </nav>}
      </section>
    </main>
  )
}
