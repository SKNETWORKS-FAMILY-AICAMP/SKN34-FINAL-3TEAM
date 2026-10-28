package com.sagomungchi.learning.record.repository

import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.mission.domain.ThinkingType
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

/**
 * 집계 대상 시도(P08) 하나의 사실. helpedBeforeFirstAnswer는 최초 답변 전 생각 열기 열람,
 * receivedFollowup은 되묻기를 받음, revised는 되묻기에 답한 보완 답변을 냄. 모두 조회 종료일까지 일어난 것만
 */
data class EligibleAttempt(
    val attemptId: UUID,
    val missionTitle: String,
    val thinkingType: ThinkingType,
    val status: AttemptStatus,
    val completed: Boolean,
    val helpedBeforeFirstAnswer: Boolean,
    val receivedFollowup: Boolean,
    val revised: Boolean,
    val lastSubmittedAt: Instant,
)

/** 시도의 최초 답변과 조회 종료일 이전 마지막 답변, 마지막 답변이 답한 되묻기 질문 */
data class AnswerPair(
    val attemptId: UUID,
    val followup: String?,
    val firstAnswerId: UUID,
    val firstText: String,
    val firstContent: AnswerContent,
    val lastAnswerId: UUID,
    val lastText: String,
    val lastContent: AnswerContent,
)

/** 근거 원문 한 건. deleted는 학생이 deleted_student에 있음 */
data class EvidenceRow(
    val answerId: UUID,
    val attemptId: UUID,
    val studentId: UUID,
    val missionTitle: String,
    val answerVersion: Int,
    val submittedAt: Instant,
    val text: String,
    val deleted: Boolean,
)

data class StatsRow(val attempts: Int, val completedAttempts: Int, val students: Int)

/** 시도별 시각 한 건 (생각 열기 열람, 돌아보기 작성) */
data class AttemptTime(val attemptId: UUID, val at: Instant)

@Mapper
interface RecordMapper {
    fun findEligible(@Param("studentId") studentId: UUID, @Param("start") start: Instant, @Param("end") end: Instant): List<EligibleAttempt>
    fun findAnswerPairs(@Param("studentId") studentId: UUID, @Param("start") start: Instant, @Param("end") end: Instant): List<AnswerPair>
    fun isRecorded(@Param("studentId") studentId: UUID, @Param("attemptId") attemptId: UUID): Boolean
    fun findEvidence(@Param("answerIds") answerIds: List<UUID>): List<EvidenceRow>
    fun stats(@Param("start") start: Instant, @Param("end") end: Instant): StatsRow
    fun findHintUsages(@Param("attemptIds") attemptIds: List<UUID>): List<AttemptTime>
    fun findReflectionTimes(@Param("attemptIds") attemptIds: List<UUID>): List<AttemptTime>
}
