package com.sagomungchi.core.report.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.repository.ReportJobRetryRepository
import org.springframework.context.ApplicationEventPublisher
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class ReportAdminRetryService(private val jobs: ReportJobRepository, private val retries: ReportJobRetryRepository,
    private val access: ReportAccessService, private val students: StudentAccessService,
    private val creation: ReportJobService, private val events: ApplicationEventPublisher) {
    @Transactional
    fun request(originalId: UUID, key: UUID, actor: AuthenticatedAccount): ReportRetryAccepted {
        if (actor.session.role != "ADMIN") forbidden()
        // Authorization is checked before any durable replay, in addition to the HTTP filter.
        if ("SERVICE_OPS" !in actor.permissions) forbidden()
        retries.byKey(actor.account.id,key)?.let { existing ->
            if (existing.originalJobId != originalId)
                throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"IDEMPOTENCY_KEY_REUSED","같은 키에 다른 작업을 사용할 수 없습니다.")
            return existing.accepted()
        }
        val original = jobs.find(originalId) ?: missing()
        access.regeneration(actor,original.studentId)
        students.requireReportRetryActive(original.studentId)
        jobs.lockWeek(original.studentId,original.periodFrom)
        val locked = jobs.lock(originalId) ?: missing()
        retries.byOriginal(originalId)?.let {
            throw BusinessException(HttpStatus.CONFLICT,"REPORT_ALREADY_RETRIED","이미 재처리 작업이 접수됐습니다. 연결된 새 작업을 확인해 주세요.")
        }
        if (locked.status != ReportJobStatus.FAILED)
            throw BusinessException(HttpStatus.CONFLICT,"JOB_NOT_FAILED","실패한 작업만 재처리할 수 있습니다.")
        if (jobs.inProgress(locked.studentId,locked.periodFrom))
            throw BusinessException(HttpStatus.CONFLICT,"REPORT_GENERATION_IN_PROGRESS","같은 주 리포트를 생성하고 있습니다.")
        val accepted = creation.enqueueAdminRetry(locked,actor.account.id)
        val created = requireNotNull(jobs.find(accepted.jobId))
        val retry = ReportJobRetry(originalId,created.id,actor.account.id,key,created.createdAt.toInstant())
        retries.insert(retry)
        events.publishEvent(ReportRetryRequested(retry))
        return retry.accepted()
    }
    fun origin(job: UUID) = retries.byJob(job)
    fun successor(job: UUID) = retries.byOriginal(job)
    private fun missing(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND,"JOB_NOT_FOUND","작업을 찾을 수 없습니다.")
    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","SERVICE_OPS 관리자 권한이 필요합니다.")
}
