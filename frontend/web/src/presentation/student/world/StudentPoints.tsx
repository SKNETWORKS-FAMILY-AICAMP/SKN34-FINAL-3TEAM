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
export function StudentPoints({ child }: { child: Child }) {
  const points = useMyPoints(child.id)
  const [decorating, setDecorating] = useState(false)
  return (
    <main className="st-paper st-sheet st-points-page">
      <h1>
        <Coins aria-hidden="true" /> 내 포인트
      </h1>
      {points.isPending && <p role="status">포인트를 확인하고 있어요.</p>}
      <ErrorNotice error={points.error} retry={() => void points.refetch()} />
      {points.data && (
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
      <p className="st-meta">답이 맞았는지와는 상관없이, 끝까지 해 본 만큼 쌓여요. 다른 친구와 견주지 않아요.</p>
      {decorating && (
        <Modal title="내 생각 지도 꾸미기" onClose={() => setDecorating(false)}>
          <Customize child={child} onDone={() => setDecorating(false)} />
        </Modal>
      )}
    </main>
  )
}
