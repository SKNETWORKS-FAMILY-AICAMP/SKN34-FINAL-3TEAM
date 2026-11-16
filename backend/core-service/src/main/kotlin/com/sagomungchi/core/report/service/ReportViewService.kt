package com.sagomungchi.core.report.service

import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

data class ReportViewAccess(val narrativeEnabled: Boolean, val parentSharingEnabled: Boolean)

@Service
class ReportViewService(private val repository: ReportJobRepository, private val access: ReportAccessService,
    private val products: com.sagomungchi.core.payment.service.ProductEntitlementService,
    private val entitlements: ReportEntitlementService,
    private val accounts: com.sagomungchi.core.account.service.AccountAccessService,
    @Qualifier("reportClock") private val clock: Clock,
    private val learningContext: com.sagomungchi.core.guardianship.service.StudentLearningContextService) {
    /** HTTP has finished; lock parent -> student only for final authorization and view accounting. */
    @Transactional
    fun recordWithSharing(reportId: UUID, studentId: UUID, parent: UUID, requestedNarrative: Boolean): ReportViewAccess {
        val narrative = record(reportId, studentId, parent, requestedNarrative)
        return ReportViewAccess(narrative, learningContext.sharingEnabled(studentId))
    }

    @Transactional
    fun record(reportId: UUID, studentId: UUID, parent: UUID, requestedNarrative: Boolean, premiumRequired: Boolean=false, sharingRequired: Boolean=false): Boolean {
        accounts.lockParent(parent)
        access.requireGuardian(parent, studentId)
        if (sharingRequired) learningContext.requireShared(studentId)
        val shared = learningContext.sharingEnabled(studentId)
        // Only a narrative request consults the product, so daily views never depend on payment (P24).
        val narrative=shared && (requestedNarrative || premiumRequired) && entitlements.narrativeEnabled(studentId)
        if(premiumRequired && !narrative) throw com.sagomungchi.core._common.exception.BusinessException(
            org.springframework.http.HttpStatus.FORBIDDEN,"REPORT_PREMIUM_REQUIRED","이 파일은 유료 서술을 포함합니다. 수치 전용 리포트가 필요합니다.")
        if(requestedNarrative && narrative) products.reportViewed(parent,studentId,reportId)
        repository.view(reportId, parent, OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC))
        return requestedNarrative && narrative
    }
}
