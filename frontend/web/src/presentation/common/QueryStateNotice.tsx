import type { ReactNode } from 'react'
import type { QueryState } from '../../domain/queryState.ts'

export function QueryStateNotice({ state, children }: { state: QueryState; children?: ReactNode }) {
  if (state === 'OK') return children
  const labels = {
    NO_RECORD: '아직 기록이 없습니다.',
    INSUFFICIENT_SAMPLE: '기록이 5건보다 적어 비율 대신 개수로 표시합니다.',
    PROCESSING: '처리 중입니다.',
    FAILED: '조회에 실패했습니다. 기록 없음과는 다른 상태입니다.',
  }
  return (
    <div
      className={state === 'FAILED' ? 'ux-error' : 'ux-help'}
      role={state === 'FAILED' ? 'alert' : 'status'}
      data-query-state={state}
    >
      {children ?? labels[state]}
    </div>
  )
}
