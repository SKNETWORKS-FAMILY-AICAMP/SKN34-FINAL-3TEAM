package com.sagomungchi.core.admin.domain

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

enum class OperationJobType { CONVERSATION, REPORT, NOTIFICATION }
enum class OperationJobStatus { QUEUED, RUNNING, COMPLETED, FAILED }
data class OperationPeriod(val from: LocalDate, val to: LocalDate) {
    fun start(): Instant = from.atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant()
    fun end(): Instant = to.plusDays(1).atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant()
}

data class OperationPage<T>(val items: List<T>, val page: Int, val size: Int, val totalElements: Long)

data class OperationJobRow(val jobId: UUID, val status: String, val retryCount: Int, val failureReason: String?, val createdAt: Instant)
data class OperationExecution(val executionId: UUID, val attemptNo: Int, val status: String, val errorCode: String?,
    val triggeredBy: UUID?, val startedAt: Instant, val finishedAt: Instant?)
data class OperationJob(val jobId: UUID, val type: OperationJobType, val status: String, val retryCount: Int,
    val failureReason: String?, val createdAt: Instant, val executions: List<OperationExecution>,
    val retryable: Boolean, val retryUnavailableReason: String?)
data class OperationCount(val type: OperationJobType, val status: String, val count: Long)
data class OperationAudit(val id: UUID, val actorUserId: UUID, val action: String, val targetType: String,
    val targetId: UUID?, val result: String, val createdAt: Instant)
/** Free text from providers and legacy columns never becomes an operator-facing error. */
object OperationErrors {
    private val safe = setOf("REDIS_PUBLISH_FAILED","GENERATION_FAILED","GENERATOR_NOT_CONFIGURED",
        "JOB_RETRY_UNAVAILABLE","JOB_NOT_FAILED","JOB_RETRY_IN_PROGRESS","SUPERSEDED","AI_UNAVAILABLE",
        "AI_TIMEOUT","STREAM_DISCONNECTED","CONVERSATION_FAILED",
        "STREAM_INTERRUPTED","ANALYSIS_FAILED","ANALYSIS_TIMEOUT","AI_INVALID_RESPONSE","LEARNING_INVALID_RESPONSE","USAGE_LIMIT_REACHED","ANALYSIS_USAGE_UNAVAILABLE","CHILD_NOT_LINKED","CONSENT_REQUIRED","PAYMENT_ENTITLEMENT_UNAVAILABLE","PRODUCT_FEATURE_DISABLED","FORBIDDEN","STUDENT_DELETED","REPORT_NOT_CREATED","REPORT_EXECUTION_ABANDONED")
    fun code(value: String?): String? = value?.let { if (it in safe) it else "REDACTED_ERROR" }
}
