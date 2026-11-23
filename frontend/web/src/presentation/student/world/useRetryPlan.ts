import { useEffect, useState } from 'react'
import { useFetchWeeklyTheme } from '../../../data/retention/queries.ts'
import { retryPlan } from '../../../domain/retention.ts'
import type { RetryPlan, WeeklyTheme } from '../../../domain/retention.ts'

/**
 * 끝낸 문제의 '다시 풀기'를 어떻게 보일지(#807, domain `retryPlan`). 테마 문제일 수 있으면 화면을 열 때 주간 테마를 새로 받는다:
 * 캐시가 문제를 끝내기 전 것이면 그 요일이 '푸는 중'으로 남아 오늘 장면이 이미 끝낸 문제를 `THEME_DAY`로 시작하려 하기 때문.
 * 주간 테마를 못 받으면 테마 문제는 다시 풀기를 보이지 않는다.
 */
export function useRetryPlan(isTheme: boolean | null, missionId: string, childId: string | undefined, enabled: boolean): RetryPlan {
  const fetchTheme = useFetchWeeklyTheme(childId)
  const [theme, setTheme] = useState<WeeklyTheme | null | undefined>(undefined)
  const need = enabled && isTheme !== false && !!childId
  useEffect(() => {
    if (!need) return
    let live = true
    fetchTheme().then((t) => { if (live) setTheme(t ?? null) }, () => { if (live) setTheme(null) })
    return () => { live = false }
  }, [need, missionId]) // eslint-disable-line react-hooks/exhaustive-deps
  return retryPlan(isTheme, missionId, childId ? theme : null)
}
