/** 오류 응답 (API 명세서 1.3, RFC 9457) */
export interface ProblemDetail {
  type?: string
  title: string
  status: number
  code: string
  detail?: string
  instance?: string
  traceId?: string
  errors?: { field: string; reason: string }[]
  retryable?: boolean
  latest?: unknown
  missingFields?: string[]
  /** STUDENT_PIN_INVALID의 남은 시도 횟수 (API 명세 3.11) */
  remainingAttempts?: number
}
