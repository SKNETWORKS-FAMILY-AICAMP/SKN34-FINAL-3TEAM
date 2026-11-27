/**
 * 추가 문제(EXTRA) 시작이 막혔을 때 아이에게 보일 말(#1093). 서버 문구의 이용권·프리미엄·KST·시도 같은 말을 그대로 보이지 않는다.
 * - 429 USAGE_LIMIT_REACHED: 무료 상품에서 추가 문제를 다시 켠 경우의 하루 한도
 * - 403 PREMIUM_REQUIRED: 무료 학생의 추가 문제(기본, #487)
 * 막힌 뒤에는 같은 화면에서 다시 시작해도 같은 답이라 시작 단추를 끈다.
 */
export const STUDENT_START_BLOCKED = {
  USAGE_LIMIT_REACHED: '오늘 더 풀어 볼 문제는 다 열었어요. 내일 또 새 문제를 열 수 있어요! 하던 문제는 내 공책에서 이어서 풀 수 있어요.',
  PREMIUM_REQUIRED: '이 문제는 지금은 열 수 없어요. 오늘 문제를 먼저 풀어 봐요!',
} as const

/** ApiError(problem.code)든 같은 모양의 값이든 코드만 본다 */
export function startBlockedMessage(error: unknown): string | null {
  const code = (error as { problem?: { code?: unknown } } | null)?.problem?.code
  return code === 'USAGE_LIMIT_REACHED' || code === 'PREMIUM_REQUIRED' ? STUDENT_START_BLOCKED[code] : null
}
