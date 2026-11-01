package com.sagomungchi.core.report.domain

import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.temporal.TemporalAdjusters
import java.util.UUID

data class ReportPeriod(val from: LocalDate, val to: LocalDate) {
    init { require(from.dayOfWeek == DayOfWeek.MONDAY && to == from.plusDays(6)) }
    companion object {
        val ZONE: ZoneId = ZoneId.of("Asia/Seoul")
        fun previousWeek(at: Instant): ReportPeriod {
            val monday = at.atZone(ZONE).toLocalDate().with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
            return ReportPeriod(monday.minusWeeks(1), monday.minusDays(1))
        }
    }
}

enum class ReportJobStatus {
    QUEUED, RUNNING, COMPLETED, FAILED;
    fun canTransitionTo(next: ReportJobStatus): Boolean = when (this) {
        QUEUED -> next in setOf(RUNNING, COMPLETED, FAILED)
        RUNNING -> next in setOf(COMPLETED, FAILED)
        COMPLETED, FAILED -> false
    }
}
enum class ReportTrigger { SCHEDULE, REGENERATE, ADMIN_RETRY }

data class ReportJob(
    val id: UUID,
    val studentId: UUID,
    val periodFrom: LocalDate,
    val periodTo: LocalDate,
    val trigger: ReportTrigger,
    val requestedBy: UUID?,
    val status: ReportJobStatus,
    val reportId: UUID?,
    val failureReason: String?,
    val createdAt: OffsetDateTime,
    val startedAt: OffsetDateTime?,
    val completedAt: OffsetDateTime?,
)

/** #44 can persist idempotent notifications in a BEFORE_COMMIT listener. No transport here. */
data class ReportJobFinished(val sourceEventId: UUID, val jobId: UUID, val studentId: UUID,
    val reportId: UUID, val status: ReportJobStatus)

/** Every committed terminal transition, including recovery/deletion without a report ID. */
data class ReportJobOutcomeRecorded(val sourceEventId: UUID, val jobId: UUID, val status: ReportJobStatus) {
    init { require(status in setOf(ReportJobStatus.COMPLETED, ReportJobStatus.FAILED)) }
}

/** Validated lifecycle command. Transport envelopes/JSON remain in the consumer. */
data class ReportLifecycleEvent(val eventId: UUID, val jobId: UUID, val studentId: UUID,
    val reportId: UUID, val status: ReportJobStatus, val failureReason: String? = null) {
    init {
        require(status != ReportJobStatus.QUEUED)
        require(if (status == ReportJobStatus.FAILED) failureReason?.matches(Regex("[A-Z][A-Z0-9_]{0,99}")) == true
            else failureReason == null)
    }
    val eventType: String get() = when (status) {
        ReportJobStatus.RUNNING -> "report.started"
        ReportJobStatus.COMPLETED -> "report.completed"
        ReportJobStatus.FAILED -> "report.failed"
        ReportJobStatus.QUEUED -> error("A lifecycle event cannot enqueue a job")
    }
}

data class ReportJobAccepted(val jobId: UUID, val childId: UUID, val period: ReportPeriod,
    val status: ReportJobStatus = ReportJobStatus.QUEUED)

/** Validated internal recovery result; never contains report contents or URLs. */
data class ReportReconciliation(val jobId: UUID, val studentId: UUID, val period: ReportPeriod,
    val status: String, val reportId: UUID?, val failureReason: String?) {
    init {
        require(status in setOf("BUSY", "COMPLETED", "FAILED"))
        require(if (status == "FAILED") failureReason?.matches(Regex("[A-Z][A-Z0-9_]{0,99}")) == true else failureReason == null)
        require(status != "COMPLETED" || reportId != null)
        require(status != "BUSY" || reportId == null)
    }
}
