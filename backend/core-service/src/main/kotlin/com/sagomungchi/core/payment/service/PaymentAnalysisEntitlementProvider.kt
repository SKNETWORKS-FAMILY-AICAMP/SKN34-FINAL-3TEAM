package com.sagomungchi.core.payment.service

import com.sagomungchi.core.conversation.service.AnalysisEntitlement
import com.sagomungchi.core.conversation.service.AnalysisEntitlementProvider
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.conflict
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.ZoneId
import java.util.UUID

/** Implements the exact #41 consumer port; conversation orchestration and Redis remain its owner. */
@Service
class PaymentAnalysisEntitlementProvider(private val products: ProductEntitlementService): AnalysisEntitlementProvider {
    override fun entitlement(parentId: UUID,childId: UUID): AnalysisEntitlement {
        val value=products.forParent(parentId,childId)
        val limit=value.product.limits["dailyConversations"]
        if(limit !is Int || limit<0) unavailable("PAYMENT_ENTITLEMENT_UNAVAILABLE")
        val end=when(value.status) { "ACTIVE" -> value.periodEnd; "RENEWAL_FAILED" -> value.graceUntil; else -> null }
        return AnalysisEntitlement(value.product.id,limit,end?.atTime(9,0)?.atZone(ZoneId.of("Asia/Seoul"))?.toInstant(),value.conversationEnabled)
    }
    @Transactional(propagation=Propagation.MANDATORY)
    override fun recordAttempt(parentId: UUID,childId: UUID,sourceId: UUID) {
        if(!entitlement(parentId,childId).conversationEnabled) conflict("PRODUCT_FEATURE_DISABLED")
        val permit=products.beginUsage(parentId,childId,"CONVERSATION",sourceId)
        val reservation=permit.reservationId ?: conflict("PRODUCT_FEATURE_DISABLED")
        // #41 admission counts an analysis attempt, including retries/failures, as premium usage.
        products.finishUsage(childId,reservation,true)
    }
}
