import type { StudentLook } from '../../domain/studentLook.ts'

// 개발 목업 전용: 학생별 꾸미기 설정. 새로고침해도 유지되도록 sessionStorage에 가상 값만 둔다.
const lookKey = 'sagomungchi:msw-look:v1'
export const mockLooks = new Map<string, StudentLook>()
if (typeof sessionStorage !== 'undefined') {
  try {
    const raw = sessionStorage.getItem(lookKey)
    if (raw) for (const [id, look] of Object.entries(JSON.parse(raw) as Record<string, StudentLook>)) mockLooks.set(id, look)
  } catch {
    /* 손상된 개발 상태는 버린다 */
  }
}
export function persistLooks() {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(lookKey, JSON.stringify(Object.fromEntries(mockLooks)))
  } catch {
    /* 저장소를 못 쓰면 메모리 값만 유지 */
  }
}
