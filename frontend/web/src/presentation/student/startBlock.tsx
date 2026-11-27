import { startBlockedMessage } from '../../domain/studentStart.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

/** 시작 실패 안내(#1093): 한도·프리미엄 막힘이면 아이 말로, 그 밖의 오류는 공통 오류 상자 */
export function StartError({ error }: { error: unknown }) {
  const blocked = startBlockedMessage(error)
  if (blocked) return <p className="st-premium-note" role="status">{blocked}</p>
  return <ErrorNotice error={error} />
}
