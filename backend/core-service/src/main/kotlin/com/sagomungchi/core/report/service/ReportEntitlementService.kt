package com.sagomungchi.core.report.service

import org.springframework.stereotype.Service
import java.util.UUID

/**
 * Payment owns product data and subscription validity. Every report-content decision that depends on the product
 * goes through this class, so a policy change edits one place.
 */
@Service
class ReportEntitlementService(private val products: com.sagomungchi.core.payment.service.ProductEntitlementService) {
    /** P13: weekly AI narrative is premium only. Callers skip it for periods without narrative ([ReportPeriodType.narrative]). */
    fun narrativeEnabled(studentId: UUID): Boolean = products.forStudent(studentId).narrativeEnabled

    /**
     * P24 "free and premium alike": the daily problem details (followups, final answer, reflection, quotes) are
     * returned regardless of product. Open decision against P13 (free = numbers only); if it changes, return the
     * product rule here and [ReportQueryService] keeps only the numeric fields of `problems[]`.
     */
    @Suppress("UNUSED_PARAMETER")
    fun dailyDetailEnabled(studentId: UUID): Boolean = true
}
