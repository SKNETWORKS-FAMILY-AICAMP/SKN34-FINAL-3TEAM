package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/**
 * 판정과 시도 타임라인. 타임라인은 answer 테이블을 읽지만 AnswerService가 AttemptService를 쓰므로
 * 순환을 피해 judgment에서 조회 (class-diagram 4.1 AttemptService --> JudgmentService : 타임라인). 트랜잭션은 시작하지 않음
 */
@Repository
class JudgmentRepository(private val mapper: JudgmentMapper) {
    /** 답변 제출 시 PENDING 판정 (ERD 4.2, 판정 실행은 피드백 요청) */
    fun insertPending(answerId: UUID, rubricVersionId: UUID, now: Instant) {
        check(mapper.insertPending(UUID.randomUUID(), answerId, rubricVersionId, now) == 1)
    }

    /** 시도의 가장 최근 되묻기가 아직 답을 받지 않았으면 그 ID */
    fun findUnansweredLatestFollowupId(attemptId: UUID): UUID? = mapper.findUnansweredLatestFollowupId(attemptId)

    /** 버전 순 */
    fun findTimeline(attemptId: UUID): List<TimelineAnswer> = mapper.findTimeline(attemptId)
}
