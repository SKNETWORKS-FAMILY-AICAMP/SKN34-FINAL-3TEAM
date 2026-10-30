package com.sagomungchi.core.admin.service

import com.sagomungchi.core.admin.repository.OperationsRepository
import com.sagomungchi.core.report.domain.ReportJobOutcomeRecorded
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportRetryRequested
import com.sagomungchi.core.report.service.ReportAdminRetryService
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional

@Service
class ReportRetryAuditService(private val repository: OperationsRepository, private val reports: ReportAdminRetryService) {
    @Transactional(propagation = Propagation.MANDATORY)
    fun requested(event: ReportRetryRequested) {
        repository.reportRetryAudit(event.retry,"JOB_RETRY_REQUESTED","SUCCESS",null)
    }
    @Transactional(propagation = Propagation.MANDATORY)
    fun finished(event: ReportJobOutcomeRecorded) {
        val retry = reports.origin(event.jobId) ?: return
        val action = when(event.status) {
            ReportJobStatus.COMPLETED -> "JOB_RETRY_COMPLETED"
            ReportJobStatus.FAILED -> "JOB_RETRY_FAILED"
            else -> return
        }
        repository.reportRetryAudit(retry,action,
            if (event.status == ReportJobStatus.COMPLETED) "SUCCESS" else "FAILURE",event.sourceEventId)
    }
}
