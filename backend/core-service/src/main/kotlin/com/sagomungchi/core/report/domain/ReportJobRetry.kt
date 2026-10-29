package com.sagomungchi.core.report.domain

import java.time.Instant
import java.util.UUID

/** Immutable acceptance record; also reconstructs a lost idempotency response. */
data class ReportJobRetry(val originalJobId: UUID, val jobId: UUID, val requestedBy: UUID,
    val idempotencyKey: UUID, val acceptedAt: Instant) {
    fun accepted() = ReportRetryAccepted(originalJobId, jobId, acceptedAt = acceptedAt)
}
data class ReportRetryAccepted(val originalJobId: UUID, val jobId: UUID,
    val type: String = "REPORT", val status: String = "QUEUED", val acceptedAt: Instant)
data class ReportRetryRequested(val retry: ReportJobRetry)
