package com.sagomungchi.core.payment.service

import com.sagomungchi.core.payment.domain.*
import com.sagomungchi.core.payment.repository.PaymentRepository
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.conflict
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.forbidden
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.fasterxml.jackson.databind.ObjectMapper
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

data class UsagePermit(val reservationId: UUID?, val premium: Boolean)

@Service
class ProductEntitlementService(private val repository: PaymentRepository, private val tx: PaymentTransactions,
    private val students: StudentAccessService, private val json: ObjectMapper,
    @Value("\${app.payment.free-product-id:}") private val freeProductId: String) {
    fun forParent(parent: UUID, student: UUID): ProductEntitlement { students.requireLinked(parent,student); return forStudent(student) }
    fun forStudent(student: UUID): ProductEntitlement {
        val current=repository.active(student)
        if(current!=null && !BillingDates.entitled(current,tx.now()) && repository.confirmingStudent(student)) unavailable("PAYMENT_ENTITLEMENT_CONFIRMING")
        val sub=current?.takeIf { BillingDates.entitled(it,tx.now()) }
        val product=if(sub != null) sub.productSnapshot?.let { json.treeToValue(it,Product::class.java) }
            ?: unavailable("PAYMENT_PRODUCT_UNAVAILABLE") else freeProduct()
        val pending=repository.refundPending(student)
        val conversations=product.limits.path("dailyConversations")
        val narrative=product.limits.path("reportNarrative")
        if(!conversations.isIntegralNumber || conversations.intValue()<0 || !narrative.isBoolean) unavailable("PAYMENT_PRODUCT_UNAVAILABLE")
        return ProductEntitlement(student,product,sub?.id,sub?.status ?: "FREE",sub?.autoRenew ?: false,
            sub?.periodEnd,sub?.graceUntil,pending,!pending && conversations.intValue()>0,!pending && narrative.booleanValue())
    }
    private fun freeProduct(): Product {
        val id=runCatching { UUID.fromString(freeProductId) }.getOrNull() ?: unavailable("PAYMENT_FREE_PRODUCT_UNAVAILABLE")
        return repository.product(id)?.takeIf { it.active && it.price == 0 } ?: unavailable("PAYMENT_FREE_PRODUCT_UNAVAILABLE")
    }
    /** #41: call before starting premium work; reserve and refund freeze serialize on the same parent row. */
    fun beginUsage(parent: UUID, student: UUID, kind: String, source: UUID): UsagePermit = tx.locked(parent) {
        students.requireLinked(parent,student)
        reserve(student,kind,source)
    }
    @Transactional
    fun beginFeedback(student: UUID, source: UUID): UsagePermit {
        val sub=repository.active(student) ?: return UsagePermit(null,false)
        return tx.locked(sub.parentUserId) { students.requireLinked(sub.parentUserId,student); reserve(student,"FEEDBACK",source) }
    }
    private fun reserve(student: UUID, kind: String, source: UUID): UsagePermit {
        require(kind in setOf("FEEDBACK","CONVERSATION","REPORT_VIEW"))
        val entitlement=forStudent(student)
        if(entitlement.refundPending) conflict("REFUND_IN_PROGRESS")
        val sub=entitlement.subscriptionId ?: return UsagePermit(null,false)
        if(kind=="CONVERSATION" && !entitlement.conversationEnabled) conflict("PRODUCT_FEATURE_DISABLED")
        if(kind=="REPORT_VIEW" && !entitlement.narrativeEnabled) return UsagePermit(null,false)
        repository.usage(kind,source)?.let {
            if(it.studentId != student) forbidden()
            if(it.status=="FAILED") conflict("PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE")
            // A failed reservation stays conservative until an explicit new source ID is used.
            return UsagePermit(it.id,true)
        }
        val row=PremiumUsage(UUID.randomUUID(),student,sub,kind,source,"RESERVED",tx.now(),tx.now())
        check(repository.reserve(row)==1)
        return UsagePermit(row.id,true)
    }
    fun finishUsage(student: UUID, reservation: UUID, used: Boolean) {
        val sub=repository.active(student) ?: conflict("PAYMENT_USAGE_STATE_CHANGED")
        tx.locked(sub.parentUserId) { repository.usageFinish(reservation,student,used,tx.now()) }
    }
    @Transactional
    fun reportViewed(parent: UUID, student: UUID, report: UUID) {
        if(repository.active(student)==null) return
        val permit=beginUsage(parent,student,"REPORT_VIEW",report)
        permit.reservationId?.let { finishUsage(student,it,true) }
    }
}
