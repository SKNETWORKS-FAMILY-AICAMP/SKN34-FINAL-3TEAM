package com.sagomungchi.learning.judgment.repository

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
}
