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
        repository.lockWeek(studentId, period.from)
        if (repository.scheduled(studentId, period.from) != null) return null
        access.requireGuardian(parent, studentId)
        return create(studentId, period, ReportTrigger.SCHEDULE, null)
    }

    @Transactional
    fun regenerate(reportId: UUID, actor: AuthenticatedAccount): ReportJobAccepted {
        val original = repository.byReport(reportId) ?: missing()
        students.lockActive(original.studentId)
        val admin = access.regeneration(actor, original.studentId)
        repository.lockWeek(original.studentId, original.periodFrom)
        if (!admin && repository.regenerations(original.studentId, original.periodFrom) > 0)
            throw BusinessException(HttpStatus.CONFLICT, "REPORT_REGENERATION_LIMIT", "이 주 리포트의 재생성 기회를 이미 사용했습니다.")
        if (repository.inProgress(original.studentId, original.periodFrom))
            throw BusinessException(HttpStatus.CONFLICT, "REPORT_GENERATION_IN_PROGRESS", "같은 주 리포트를 생성하고 있습니다.")
        return create(original.studentId, ReportPeriod(original.periodFrom, original.periodTo),
            if (admin) ReportTrigger.ADMIN_RETRY else ReportTrigger.REGENERATE, actor.account.id)
    }

    /** Caller owns source/student/week validation and the acceptance transaction. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun enqueueAdminRetry(original: ReportJob, actor: UUID): ReportJobAccepted =
        create(original.studentId, ReportPeriod(original.periodFrom,original.periodTo), ReportTrigger.ADMIN_RETRY, actor)

    private fun create(studentId: UUID, period: ReportPeriod, trigger: ReportTrigger, actor: UUID?): ReportJobAccepted {
        val narrative = entitlements.narrativeEnabled(studentId)
        val job = ReportJob(UUID.randomUUID(), studentId, period.from, period.to, trigger, actor, ReportJobStatus.QUEUED,
            null, null, OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC), null, null)
        repository.insert(job)
        writer.append(job, narrative)
        return ReportJobAccepted(job.id, studentId, period)
    }

    private fun missing(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "리포트를 찾을 수 없습니다.")
}
