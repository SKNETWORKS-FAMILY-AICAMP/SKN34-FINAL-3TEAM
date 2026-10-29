package com.sagomungchi.core.report.service

import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

@Service
class ReportViewService(private val repository: ReportJobRepository, private val access: ReportAccessService,
    private val products: com.sagomungchi.core.payment.service.ProductEntitlementService,
    private val entitlements: ReportEntitlementService,
    private val accounts: com.sagomungchi.core.account.service.AccountAccessService,
    @Qualifier("reportClock") private val clock: Clock) {
    @Transactional
    fun record(reportId: UUID, studentId: UUID, parent: UUID, requestedNarrative: Boolean, premiumRequired: Boolean=false): Boolean {
        accounts.lockParent(parent)
        access.requireGuardian(parent, studentId)
        val narrative=entitlements.narrativeEnabled(studentId)
        if(premiumRequired && !narrative) throw com.sagomungchi.core._common.exception.BusinessException(
            org.springframework.http.HttpStatus.FORBIDDEN,"REPORT_PREMIUM_REQUIRED","이 파일은 유료 서술을 포함합니다. 수치 전용 리포트가 필요합니다.")
        if(requestedNarrative && narrative) products.reportViewed(parent,studentId,reportId)
        repository.view(reportId, parent, OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC))
        return requestedNarrative && narrative
    }
}
