package com.sagomungchi.learning.attempt.repository

import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.attempt.domain.SelfCheck
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
    fun finish(attempt: Attempt): Int
    fun complete(attempt: Attempt): Int
    fun insertReflection(
        @Param("id") id: UUID,
        @Param("attemptId") attemptId: UUID,
        @Param("reflection") reflection: Reflection,
        @Param("createdAt") createdAt: Instant,
    ): Int
    fun findReflection(attemptId: UUID): Reflection?
    fun upsertSelfAssessments(@Param("attemptId") attemptId: UUID, @Param("checks") checks: List<SelfCheck>, @Param("now") now: Instant): Int
    fun findSelfAssessments(attemptId: UUID): List<SelfCheck>
    fun insertHintUsage(
        @Param("id") id: UUID,
        @Param("attemptId") attemptId: UUID,
        @Param("hintQuestionId") hintQuestionId: UUID,
        @Param("openedAt") openedAt: Instant,
    ): Int
    fun findOpenedHintIds(attemptId: UUID): List<UUID>
}
