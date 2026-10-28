package com.sagomungchi.learning.attempt.repository

import com.sagomungchi.learning.attempt.domain.Attempt
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

@Mapper
interface AttemptMapper {
    fun insertIfNoneInProgress(attempt: Attempt): Int
    fun findInProgress(@Param("studentId") studentId: UUID, @Param("missionId") missionId: UUID): Attempt?
    fun findById(id: UUID): Attempt?
    fun findByIdForUpdate(id: UUID): Attempt?
    fun insertHintUsage(
        @Param("id") id: UUID,
        @Param("attemptId") attemptId: UUID,
        @Param("hintQuestionId") hintQuestionId: UUID,
        @Param("openedAt") openedAt: Instant,
    ): Int
    fun findOpenedHintIds(attemptId: UUID): List<UUID>
}
