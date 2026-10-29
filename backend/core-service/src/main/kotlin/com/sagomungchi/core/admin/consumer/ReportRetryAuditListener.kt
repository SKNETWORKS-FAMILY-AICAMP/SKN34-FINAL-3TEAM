package com.sagomungchi.core.admin.consumer

import com.sagomungchi.core.admin.service.ReportRetryAuditService
import com.sagomungchi.core.report.domain.ReportJobOutcomeRecorded
import com.sagomungchi.core.report.domain.ReportRetryRequested
import org.springframework.stereotype.Component
import org.springframework.transaction.event.TransactionPhase
import org.springframework.transaction.event.TransactionalEventListener

@Component
class ReportRetryAuditListener(private val service: ReportRetryAuditService) {
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    fun requested(event: ReportRetryRequested) = service.requested(event)
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    fun finished(event: ReportJobOutcomeRecorded) = service.finished(event)
}
