package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.BankQuestion
import com.sagomungchi.learning.judgment.domain.Followup
import com.sagomungchi.learning.judgment.domain.FollowupType
import com.sagomungchi.learning.judgment.domain.StoredFollowup
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** 되묻기와 질문 은행 (class-diagram 4.2 FollowupRepository). 트랜잭션은 시작하지 않음 */
@Repository
class FollowupRepository(private val mapper: FollowupMapper) {
    fun insert(judgmentId: UUID, followup: Followup, now: Instant) {
        check(mapper.insert(UUID.randomUUID(), judgmentId, followup, now) == 1)
    }

    fun countByAttempt(attemptId: UUID): Int = mapper.countByAttempt(attemptId)

    /** 같은 유형의 활성 질문 중 이 시도에서 아직 쓰지 않은 것을 먼저, 그다음 생성 순 */
    fun findBankQuestion(attemptId: UUID, type: FollowupType): BankQuestion? = mapper.findBankQuestion(attemptId, type.name)

    /** 판정이 끝난(DONE) 답변의 되묻기. 시도 전체(attemptId) 또는 답변 하나(answerId) */
    fun findStored(attemptId: UUID?, answerId: UUID?): List<StoredFollowup> = mapper.findStored(attemptId, answerId)
}
