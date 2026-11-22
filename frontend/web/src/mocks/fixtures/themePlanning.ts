import { retentionState } from './retention.ts'
import { ApiError } from '../../data/apiClient.ts'

const key='mock-theme-planning-v1'
const assigned=():Record<string,string> => JSON.parse(localStorage.getItem(key)??'{}') as Record<string,string>
export function plannedWeek(id:string) { return assigned()[id] ?? null }
export function assignWeek(id:string,week:string|null) {
  const data=assigned()
  if(week===null) delete data[id]
  else data[id]=week
  localStorage.setItem(key,JSON.stringify(data))
}
export function weekLocked(grade:string,week:string) {
  return retentionState.themes.some(t=>t.grade===grade && t.weekStart===week && t.status==='PUBLISHED')
}
export function requireOpenWeek(grade:string,week:string) {
  if(weekLocked(grade,week)) throw new ApiError({status:409,code:'WEEK_LOCKED',title:'이미 게시가 확정된 주차입니다.'})
}
