import { callTypeLabels, labelOf, usageGroupByLabels } from '../../domain/admin/operations.ts'
import type { UsageGroupBy, UsageItem } from '../../domain/admin/operations.ts'

/** AI 사용량 표 열(#1051). 첫 열 제목만 묶음 기준을 따른다 */
export function usageColumns(groupBy: UsageGroupBy) {
  return [groupBy === 'DAY' ? '날짜 (KST)' : usageGroupByLabels[groupBy], '호출 / 실패', '실패율', '평균 지연', 'p50 지연', 'p95 지연', '입력 / 출력 토큰', '비용 (USD)']
}

const weekdays = ['일', '월', '화', '수', '목', '금', '토']

/** 묶음 값 표시. 값이 기록되지 않은 묶음(null)은 무엇이 비었는지 말로 적는다 */
export function usageKeyLabel(groupBy: UsageGroupBy, key: string | null) {
  if (key == null) return groupBy === 'ERROR_CODE' ? '오류 코드 없음 (성공 포함)' : '기록 없음'
  if (groupBy === 'CALL_TYPE') return labelOf(callTypeLabels, key)
  if (groupBy === 'DAY' && /^\d{4}-\d{2}-\d{2}$/.test(key)) return `${key} (${weekdays[new Date(key + 'T00:00:00Z').getUTCDay()]})`
  return key
}

/** 실패율은 응답에 없고 failures / calls로 계산한다 (api-spec #1051) */
export const failureRate = (u: Pick<UsageItem, 'calls' | 'failures'>) =>
  u.calls ? `${(Math.round((u.failures / u.calls) * 1000) / 10).toFixed(1)}%` : '미측정'

export const latency = (ms: number) => `${Math.round(ms).toLocaleString('ko-KR')}ms`
