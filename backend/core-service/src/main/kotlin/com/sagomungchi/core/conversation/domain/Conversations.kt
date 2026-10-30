package com.sagomungchi.core.conversation.domain

import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.exception.ErrorKind

data class AnalysisScope(val childId: UUID, val from: LocalDate, val to: LocalDate, val changed: Boolean = false) {
    init { if (from > to) invalid("기간 시작은 종료 이전이어야 합니다.") }
    companion object {
        fun of(childId: UUID, from: LocalDate?, to: LocalDate?): AnalysisScope {
            if ((from == null) != (to == null)) invalid("from·to를 함께 지정해 주세요.")
            val today = LocalDate.now(ZoneId.of("Asia/Seoul"))
            return AnalysisScope(childId, from ?: today.minusDays(6), to ?: today)
        }
    }
}
data class ConversationRow(val id: UUID, val parentUserId: UUID, val studentId: UUID,
    val periodFrom: LocalDate, val periodTo: LocalDate, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime) {
    fun scope() = AnalysisScope(studentId, periodFrom, periodTo)
}
data class MessageRow(val id: UUID, val conversationId: UUID, val seq: Int, val question: String,
    val answer: String?, val scopeStudentId: UUID?, val scopeFrom: LocalDate?, val scopeTo: LocalDate?,
    val scopeChanged: Boolean, val status: String, val source: String?, val clarification: String?,
    val metrics: String?, val verification: String?, val recordCount: Int?, val failureCode: String?,
    val retryCount: Int, val createdAt: OffsetDateTime, val completedAt: OffsetDateTime?,
    val fallback: String? = null, val notice: String? = null) {
    fun scope() = scopeStudentId?.let { AnalysisScope(it, scopeFrom!!, scopeTo!!, scopeChanged) }
}
data class EvidenceRow(val id: UUID, val messageId: UUID, val attemptId: UUID, val answerId: UUID?, val answerVersion: Int?, val kind: String = "ANSWER")
fun invalid(message: String): Nothing = throw BusinessException(ErrorKind.INVALID, "VALIDATION_FAILED", message)
fun missing(): Nothing = throw BusinessException(ErrorKind.NOT_FOUND, "NOT_FOUND", "대화 또는 메시지를 찾을 수 없습니다.")
fun conflict(): Nothing = throw BusinessException(ErrorKind.CONFLICT, "ANALYSIS_IN_PROGRESS", "진행 중인 질문이 있거나 재시도할 수 없는 메시지입니다.")
