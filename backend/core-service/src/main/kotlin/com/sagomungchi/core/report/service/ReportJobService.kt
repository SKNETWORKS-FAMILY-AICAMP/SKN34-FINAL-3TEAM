package com.sagomungchi.core.report.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.messaging.ReportGenerateWriter
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.annotation.Propagation
import java.time.Clock
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

@Service
class ReportJobService(private val repository: ReportJobRepository, private val writer: ReportGenerateWriter,
    private val students: com.sagomungchi.core.guardianship.service.StudentAccessService,
    private val access: ReportAccessService, private val entitlements: ReportEntitlementService,
    @Qualifier("reportClock") private val clock: Clock) {
    @Transactional
    fun scheduled(parent: UUID, studentId: UUID, period: ReportPeriod): ReportJobAccepted? {
        students.lockActive(studentId)
        repository.lockPeriod(studentId, period)
        if (repository.scheduled(studentId, period) != null) return null
        access.requireGuardian(parent, studentId)
        return create(studentId, period, ReportTrigger.SCHEDULE, null)
    }

    @Transactional
    fun regenerate(reportId: UUID, actor: AuthenticatedAccount): ReportJobAccepted {
        val original = repository.byReport(reportId) ?: missing()
        students.lockActive(original.studentId)
        val admin = access.regeneration(actor, original.studentId)
        val period = original.period
        repository.lockPeriod(original.studentId, period)
        if (!admin && repository.regenerations(original.studentId, period) > 0)
            throw BusinessException(HttpStatus.CONFLICT, "REPORT_REGENERATION_LIMIT", "${label(period)} 리포트의 재생성 기회를 이미 사용했습니다.")
        if (repository.inProgress(original.studentId, period))
            throw BusinessException(HttpStatus.CONFLICT, "REPORT_GENERATION_IN_PROGRESS", "같은 ${label(period)} 리포트를 생성하고 있습니다.")
        return create(original.studentId, period, if (admin) ReportTrigger.ADMIN_RETRY else ReportTrigger.REGENERATE, actor.account.id)
    }

    /** Caller owns source/student/week validation and the acceptance transaction. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun enqueueAdminRetry(original: ReportJob, actor: UUID): ReportJobAccepted =
        create(original.studentId, original.period, ReportTrigger.ADMIN_RETRY, actor)

    private fun create(studentId: UUID, period: ReportPeriod, trigger: ReportTrigger, actor: UUID?): ReportJobAccepted {
        // Daily has no narrative; a payment outage must not block its command (P24).
        val narrative = period.type.narrative && entitlements.narrativeEnabled(studentId)
        val job = ReportJob(UUID.randomUUID(), studentId, period.type, period.from, period.to, trigger, actor, ReportJobStatus.QUEUED,
            null, null, OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC), null, null)
        repository.insert(job)
        writer.append(job, narrative)
        return ReportJobAccepted(job.id, studentId, period)
    }

    private fun label(period: ReportPeriod) = if (period.type == ReportPeriodType.DAILY) "이 날" else "이 주"

    private fun missing(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "리포트를 찾을 수 없습니다.")
}
