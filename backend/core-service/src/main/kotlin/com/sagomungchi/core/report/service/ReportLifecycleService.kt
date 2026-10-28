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
    private val events: ApplicationEventPublisher, @Qualifier("reportClock") private val clock: Clock) {
    @Transactional
    fun apply(event: ReportLifecycleEvent) {
        val status = event.status
        if (!processed.markProcessed(event.eventId, event.eventType)) return
        val job = requireNotNull(repository.lock(event.jobId)) { "Unknown report job" }
        require(job.studentId == event.studentId && (job.reportId == null || job.reportId == event.reportId)) { "Report job identity mismatch" }
        if (!job.status.canTransitionTo(status)) return
        val at = OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC)
        if (!repository.transition(job.id, status, event.reportId, event.failureReason, at)) return
        repository.execution(job, status, event.failureReason, at)
        if (status != ReportJobStatus.RUNNING)
            events.publishEvent(ReportJobFinished(event.eventId, job.id, job.studentId, event.reportId, status))
    }
}
