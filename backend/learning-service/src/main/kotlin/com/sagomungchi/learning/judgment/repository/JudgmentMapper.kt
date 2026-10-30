package com.sagomungchi.learning.judgment.repository

import com.sagomungchi.learning.judgment.domain.FeedbackTarget
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.judgment.domain.JudgmentElement
import com.sagomungchi.learning.judgment.domain.StoredElement
import com.sagomungchi.learning.judgment.domain.StoredJudgment
import com.sagomungchi.learning.judgment.domain.SupportTarget
import com.sagomungchi.learning.judgment.domain.SupportTargetType
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

@Mapper
interface JudgmentMapper {
    fun insertPending(
        @Param("id") id: UUID,
        @Param("answerId") answerId: UUID,
        @Param("rubricVersionId") rubricVersionId: UUID,
        @Param("createdAt") createdAt: Instant,
    ): Int
    fun findUnansweredLatestFollowupId(attemptId: UUID): UUID?
    fun findTimeline(attemptId: UUID): List<TimelineAnswer>

    fun findTarget(answerId: UUID): FeedbackTarget?
    fun findByAnswerId(answerId: UUID): Judgment?
    fun acquire(@Param("answerId") answerId: UUID, @Param("now") now: Instant, @Param("leaseUntil") leaseUntil: Instant): Int
    fun lockAttemptOpen(answerId: UUID): Boolean
    fun complete(
        @Param("judgment") judgment: Judgment,
        @Param("leaseUntil") leaseUntil: Instant,
        @Param("traceId") traceId: String?,
        @Param("now") now: Instant,
    ): Int
    fun insertElements(@Param("judgmentId") judgmentId: UUID, @Param("elements") elements: List<JudgmentElement>): Int
    fun fail(@Param("judgment") judgment: Judgment, @Param("leaseUntil") leaseUntil: Instant): Int
    fun findStored(@Param("attemptId") attemptId: UUID?, @Param("answerId") answerId: UUID?): List<StoredJudgment>
    fun findStoredElements(@Param("attemptId") attemptId: UUID?, @Param("answerId") answerId: UUID?): List<StoredElement>
    fun findSupportTarget(@Param("type") type: SupportTargetType, @Param("id") id: UUID): SupportTarget?
}
