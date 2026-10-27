package com.sagomungchi.learning.attempt.repository

import com.sagomungchi.learning.attempt.domain.Attempt
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** 학습 시도와 생각 열기 열람 기록. 트랜잭션은 시작하지 않음 */
@Repository
class AttemptRepository(private val mapper: AttemptMapper) {
    /** 같은 학생·미션의 진행 중 시도가 있으면(부분 UK) 넣지 않고 false */
    fun insertIfNoneInProgress(attempt: Attempt): Boolean = mapper.insertIfNoneInProgress(attempt) == 1

    fun findInProgress(studentId: UUID, missionId: UUID): Attempt? = mapper.findInProgress(studentId, missionId)

    fun findById(id: UUID): Attempt? = mapper.findById(id)

    fun recordHintOpened(attemptId: UUID, hintQuestionId: UUID, openedAt: Instant) {
        check(mapper.insertHintUsage(UUID.randomUUID(), attemptId, hintQuestionId, openedAt) == 1)
    }

    fun findOpenedHintIds(attemptId: UUID): Set<UUID> = mapper.findOpenedHintIds(attemptId).toSet()
}
