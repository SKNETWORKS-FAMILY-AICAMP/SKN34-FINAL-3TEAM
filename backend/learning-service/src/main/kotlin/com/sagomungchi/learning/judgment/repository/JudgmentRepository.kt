package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.FeedbackTarget
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.judgment.domain.StoredElement
import com.sagomungchi.learning.judgment.domain.StoredJudgment
import com.sagomungchi.learning.judgment.domain.SupportTarget
import com.sagomungchi.learning.judgment.domain.SupportTargetType
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/**
 * 판정·요소와 시도 타임라인. 타임라인은 answer 테이블을 읽지만 AnswerService가 AttemptService를 쓰므로
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

    /** 버전 순, 각 답변이 답한 되묻기 질문 포함 */
    fun findTimeline(attemptId: UUID): List<TimelineAnswer> = mapper.findTimeline(attemptId)

    fun findTarget(answerId: UUID): FeedbackTarget? = mapper.findTarget(answerId)

    fun findByAnswerId(answerId: UUID): Judgment? = mapper.findByAnswerId(answerId)

    /**
     * class-diagram 4.2 acquire: PENDING·FAILED·리스 만료 RUNNING일 때만 RUNNING (state-diagram 3.3 조건부 UPDATE).
     * 엔티티가 가져갈 수 있다고 본 뒤에도 그사이 다른 요청이 먼저 가져갔으면 0
     */
    fun acquire(answerId: UUID, now: Instant, leaseUntil: Instant): Int = mapper.acquire(answerId, now, leaseUntil)

    /** 답변의 시도 행을 잠그고(FOR UPDATE) 아직 마무리·완료 전인지 */
    fun lockAttemptOpen(answerId: UUID): Boolean = mapper.lockAttemptOpen(answerId)

    /** 끝난 판정 저장. 획득한 리스 값이 그대로일 때만 (늦게 끝난 이전 처리의 덮어쓰기 방지) */
    fun complete(judgment: Judgment, leaseUntil: Instant, traceId: String?, now: Instant): Boolean =
        mapper.complete(judgment, leaseUntil, traceId, now) == 1

    fun insertElements(judgment: Judgment) {
        if (judgment.elements.isNotEmpty()) check(mapper.insertElements(judgment.id, judgment.elements) == judgment.elements.size)
    }

    /** 실패 기록. 획득한 리스 값이 그대로일 때만 */
    fun fail(judgment: Judgment, leaseUntil: Instant): Boolean = mapper.fail(judgment, leaseUntil) == 1

    /** 시도의 모든 답변(attemptId) 또는 답변 하나(answerId) */
    fun findStored(attemptId: UUID?, answerId: UUID?): List<StoredJudgment> = mapper.findStored(attemptId, answerId)

    fun findStoredElements(attemptId: UUID?, answerId: UUID?): List<StoredElement> = mapper.findStoredElements(attemptId, answerId)

    /** 신고·문의 대상의 학생·시도 (#146). 없으면 null */
    fun findSupportTarget(type: SupportTargetType, id: UUID): SupportTarget? = mapper.findSupportTarget(type, id)
}
