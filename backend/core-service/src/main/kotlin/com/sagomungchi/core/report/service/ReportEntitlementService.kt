package com.sagomungchi.core.report.service

import org.springframework.stereotype.Service
import java.util.UUID

/** Payment owns product data and subscription validity. */
@Service
class ReportEntitlementService(private val products: com.sagomungchi.core.payment.service.ProductEntitlementService) {
    fun narrativeEnabled(studentId: UUID): Boolean = products.forStudent(studentId).narrativeEnabled
}
