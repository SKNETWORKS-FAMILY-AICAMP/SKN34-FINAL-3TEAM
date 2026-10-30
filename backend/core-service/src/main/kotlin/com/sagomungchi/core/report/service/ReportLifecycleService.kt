package com.sagomungchi.core.report.service

import com.sagomungchi.core._common.messaging.ProcessedEventRepository
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.context.ApplicationEventPublisher
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.OffsetDateTime
import java.time.ZoneOffset

@Service
class ReportLifecycleService(private val repository: ReportJobRepository, private val processed: ProcessedEventRepository,
    private val students: com.sagomungchi.core.guardianship.service.StudentAccessService,
    private val events: ApplicationEventPublisher, @Qualifier("reportClock") private val clock: Clock) {
    @Transactional
    fun apply(event: ReportLifecycleEvent) {
        val status = event.status
        if (!processed.markProcessed(event.eventId, event.eventType)) return
        val studentStatus = students.lockStatus(event.studentId)
        val job = requireNotNull(repository.lock(event.jobId)) { "Unknown report job" }
        require(job.studentId == event.studentId && (job.reportId == null || job.reportId == event.reportId)) { "Report job identity mismatch" }
        if (!job.status.canTransitionTo(status)) return
        if (studentStatus != "ACTIVE") {
            finish(job, ReportJobStatus.FAILED, job.reportId, "STUDENT_DELETED", false)
            return
        }
        val at = OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC)
        if (!repository.transition(job.id, status, event.reportId, event.failureReason, at)) return
        repository.execution(job, status, event.failureReason, at)
        if (status != ReportJobStatus.RUNNING)
            events.publishEvent(ReportJobFinished(event.eventId, job.id, job.studentId, event.reportId, status))
    }

    @Transactional
    fun reconcile(candidate: ReportJob, result: ReportReconciliation) {
        require(candidate.id == result.jobId && candidate.studentId == result.studentId &&
            candidate.periodFrom == result.period.from && candidate.periodTo == result.period.to) { "Report recovery identity mismatch" }
        if (result.status == "BUSY") return
        val studentStatus = students.lockStatus(candidate.studentId)
        val job = requireNotNull(repository.lock(candidate.id)) { "Unknown report job" }
        require(job.studentId == result.studentId && job.periodFrom == result.period.from && job.periodTo == result.period.to)
        // Deletion may commit while the HTTP request is in flight. It wins over late results.
        if (!job.status.canTransitionTo(ReportJobStatus.valueOf(result.status))) return
        if (studentStatus != "ACTIVE") {
            finish(job, ReportJobStatus.FAILED, job.reportId, "STUDENT_DELETED", false)
            return
        }
        require(result.reportId == null || job.reportId == null || job.reportId == result.reportId) { "Report recovery report identity mismatch" }
        finish(job, ReportJobStatus.valueOf(result.status), result.reportId, result.failureReason,
            result.reportId != null && result.failureReason != "STUDENT_DELETED")
    }

    @Transactional(propagation = org.springframework.transaction.annotation.Propagation.MANDATORY)
    fun failForDeletion(studentId: java.util.UUID) {
        // Caller holds the student row, matching generation/reconciliation lock order.
        repository.pendingForStudent(studentId).forEach {
            finish(it, ReportJobStatus.FAILED, it.reportId, "STUDENT_DELETED", false)
        }
    }

    private fun finish(job: ReportJob, status: ReportJobStatus, reportId: java.util.UUID?, reason: String?, notify: Boolean) {
        val at = OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC)
        if (!repository.transition(job.id, status, reportId, reason, at)) return
        repository.execution(job, status, reason, at)
        if (notify && reportId != null)
            events.publishEvent(ReportJobFinished(java.util.UUID.randomUUID(), job.id, job.studentId, reportId, status))
    }
}
