package com.sagomungchi.learning.attempt.repository

import com.sagomungchi.learning.attempt.domain.AttemptDraft
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** 시도당 1행 초안. 트랜잭션은 시작하지 않음 */
@Repository
class AttemptDraftRepository(private val mapper: AttemptDraftMapper) {
    fun insert(draft: AttemptDraft) {
        check(mapper.insert(draft) == 1)
    }

    fun findByAttemptId(attemptId: UUID): AttemptDraft? = mapper.findByAttemptId(attemptId)

    /** 저장된 버전이 ifMatch일 때만 next로 바꾸고 true (class-diagram 4.1 updateIfVersion, ERD 4.2) */
    fun updateIfVersion(next: AttemptDraft, ifMatch: Int): Boolean = mapper.updateIfVersion(next, ifMatch) == 1

    /** 버전 조건 없이 한 번에 갱신해 같은 순간의 초안 저장과 겹쳐도 행 잠금 순서대로 처리됨 */
    fun clearAnswer(attemptId: UUID, savedAt: Instant) {
        check(mapper.clearAnswer(attemptId, savedAt) == 1)
    }
}
