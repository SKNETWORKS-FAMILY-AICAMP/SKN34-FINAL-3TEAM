import { useState } from 'react'
import { Coins } from 'lucide-react'
import { useMyPoints } from '../../../data/retention/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { POINT_EVENT_LABELS, POINT_RULES } from '../../../domain/retention.ts'
import { ErrorNotice, Modal } from '../../shared/ClassroomParts.tsx'
import { Customize } from './Customize.tsx'
import './retention.css'

const when = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'short', timeStyle: 'short' })

/** 내 포인트 (P21, API 명세 2.10). 잔액은 나와 학부모님만 보고, 순위·소멸은 없다. */
export function StudentPoints({ child, embedded = false }: { child: Child; embedded?: boolean }) {
  const [page, setPage] = useState(0)
  const points = useMyPoints(child.id, page)
  const [decorating, setDecorating] = useState(false)
  // embedded: 학생 설정(#583) 안의 한 부분(제목 h2, 바깥 main 없음)
  const Wrapper = embedded ? 'section' : 'main', Title = embedded ? 'h2' : 'h1'
  return (
    <Wrapper className={embedded ? 'st-points-page st-settings-part' : 'st-paper st-sheet st-points-page'} aria-labelledby="points-h">
      <Title id="points-h" tabIndex={embedded ? -1 : undefined}>
        <Coins aria-hidden="true" /> 내 포인트
      </Title>
      {points.isPending && <p role="status">포인트를 확인하고 있어요.</p>}
      <ErrorNotice error={points.error} retry={() => void points.refetch()} />
      {points.data && !points.error && (
        <>
          <p className="st-balance">
            지금 <strong>{points.data.balance}</strong>포인트
          </p>
          <button type="button" className="st-button st-primary" onClick={() => setDecorating(true)}>
            꾸미기 해금하러 가기
          </button>
          <h2>쌓이고 쓴 내역</h2>
          {points.data.items.length === 0 ? (
            <p className="st-meta">아직 내역이 없어요.</p>
          ) : (
            <ul className="st-ledger">
              {points.data.items.map((e, i) => (
                <li key={`${e.createdAt}-${i}`}>
                  <span>{POINT_EVENT_LABELS[e.eventType]}</span>
                  <small>{when(e.createdAt)}</small>
                  <strong data-minus={e.amount < 0 || undefined}>
                    {e.amount > 0 ? `+${e.amount}` : e.amount}
                  </strong>
                </li>
              ))}
            </ul>
          )}
          {points.data.totalElements > points.data.size && <nav className="st-points-pages" aria-label="포인트 내역 페이지">
            <button type="button" className="st-button" disabled={page === 0 || points.isFetching} onClick={() => setPage(p => p - 1)}>이전 내역</button>
            <span>{page + 1} / {Math.ceil(points.data.totalElements / points.data.size)}쪽</span>
            <button type="button" className="st-button" disabled={(page + 1) * points.data.size >= points.data.totalElements || points.isFetching}
              onClick={() => setPage(p => p + 1)}>다음 내역</button>
          </nav>}
        </>
      )}
      <h2>포인트는 이렇게 쌓여요</h2>
      <ul className="st-rules">
        {POINT_RULES.map((r) => (
          <li key={r.type}>
            {POINT_EVENT_LABELS[r.type]} {r.amount}포인트 · {r.note}
          </li>
        ))}
      </ul>
      {decorating && (
        <Modal title="내 생각 지도 꾸미기" onClose={() => setDecorating(false)}>
          <Customize child={child} onDone={() => setDecorating(false)} />
        </Modal>
      )}
    </Wrapper>
  )
}
