import { ApiError } from '../apiClient.ts'
import type { Draft } from '../../domain/classroom.ts'
export class DraftConflictError extends ApiError {
  readonly latest: Draft
  constructor(latest: Draft) {
    super({
      code: 'ATTEMPT_DRAFT_CONFLICT',
      title: '다른 화면에 더 최신 초안이 있어요.',
      status: 409,
    })
    this.latest = latest
  }
}
