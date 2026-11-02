package com.sagomungchi.core.payment.service

import com.sagomungchi.core.payment.client.*
import com.sagomungchi.core.payment.domain.*
import com.sagomungchi.core.payment.repository.PaymentRepository
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.conflict
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.forbidden
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.missing
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import org.springframework.stereotype.Service
import java.time.Duration
import java.util.UUID

@Service
class RefundService(private val repository: PaymentRepository,private val tx: PaymentTransactions,
    private val usage: PremiumUsageClient,private val pg: TossGateway,private val payments: PaymentService) {
    fun request(parent: UUID,paymentId: UUID,reason: String): RefundRequest {
        val p=repository.paymentId(paymentId) ?: missing()
        val order=repository.order(p.orderId) ?: missing()
        if(order.parentUserId!=parent) forbidden()
        val refund=tx.locked(parent) {
            val payment=repository.paymentId(paymentId) ?: missing()
            val existing=repository.pendingRefund(order.id)
            if(existing!=null) return@locked existing
            eligible(payment)
            localUnused(order,payment)
            val r=RefundRequest(UUID.randomUUID(),payment.id,parent,payment.amount,reason,"REQUESTED",null,null,null,null,tx.now(),UUID.randomUUID(),null)
            check(repository.insertRefund(r)==1)
            check(repository.savePayment(payment.copy(status="REFUND_REVIEW",updatedAt=tx.now()))==1)
            payments.notify(order,"PAYMENT_CHANGED","REFUND_REQUESTED:${r.id}")
            r
        }
        // REQUESTED is a durable premium-use freeze before this external query.
        if(refund.status!="REQUESTED" || refund.usageVerifiedAt!=null) return refund
        val used=usage.used(order.studentId,requireNotNull(p.approvedAt))
        val result=tx.locked(parent) {
            val current=repository.refund(refund.id) ?: missing()
            if(current.status!="REQUESTED") return@locked current
            if(used) {
                val rejected=current.copy(status="REJECTED",rejectReason="결제 후 프리미엄 기능 사용",decidedAt=tx.now())
                repository.saveRefund(rejected)
                repository.savePayment((repository.paymentId(paymentId) ?: missing()).copy(status="APPROVED",updatedAt=tx.now()))
                payments.notify(order,"PAYMENT_CHANGED","REFUND_REJECTED:${current.id}")
                rejected
            } else {
                localUnused(order,repository.paymentId(paymentId) ?: missing())
                val verified=current.copy(usageVerifiedAt=tx.now())
                repository.saveRefund(verified); verified
            }
        }
        if(result.status=="REJECTED") conflict("REFUND_NOT_ALLOWED")
        return result
    }
    fun approve(actor: UUID,id: UUID): RefundRequest {
        val original=repository.refund(id) ?: missing()
        val p=repository.paymentId(original.paymentId) ?: missing()
        val order=repository.order(p.orderId) ?: missing()
        if(original.status=="COMPLETED") return original
        if(original.status=="APPROVED") { refresh(original); return repository.refund(id) ?: missing() }
        if(original.status!="REQUESTED" || original.usageVerifiedAt==null) conflict("REFUND_NOT_READY")
        val used=usage.used(order.studentId,requireNotNull(p.approvedAt))
        val prepared=tx.locked(order.parentUserId) {
            val current=repository.refund(id) ?: missing()
            if(current.status!="REQUESTED") conflict("REFUND_STATE_CHANGED")
            val payment=repository.paymentId(current.paymentId) ?: missing()
            eligible(payment,current.createdAt); localUnused(order,payment)
            if(used || current.amount!=payment.amount) conflict("REFUND_NOT_ALLOWED")
            val r=current.copy(status="APPROVED",decidedBy=actor,decidedAt=tx.now(),usageVerifiedAt=tx.now())
            check(repository.saveRefund(r)==1);tx.audit(actor,"PAYMENT_REFUND_APPROVED",id)
            payments.notify(order,"PAYMENT_CHANGED","REFUND_APPROVED:$id");r
        }
        val result=pg.cancel(p.paymentKey ?: unavailable("PAYMENT_PG_KEY_UNAVAILABLE"),p.amount,order.kind=="RENEWAL",requireNotNull(prepared.cancelKey))
        applyVerified(prepared,result)
        return repository.refund(id) ?: missing()
    }
    fun reject(actor: UUID,id: UUID,reason: String): RefundRequest {
        val refund=repository.refund(id) ?: missing(); val p=repository.paymentId(refund.paymentId) ?: missing()
        val order=repository.order(p.orderId) ?: missing()
        return tx.locked(order.parentUserId) {
            val current=repository.refund(id) ?: missing()
            if(current.status !in setOf("REQUESTED","FAILED")) conflict("REFUND_STATE_CHANGED")
            val rejected=current.copy(status="REJECTED",decidedBy=actor,rejectReason=reason,decidedAt=tx.now())
            check(repository.saveRefund(rejected)==1)
            check(repository.savePayment((repository.paymentId(p.id) ?: missing()).copy(status="APPROVED",updatedAt=tx.now()))==1)
            tx.audit(actor,"PAYMENT_REFUND_REJECTED",id); payments.notify(order,"PAYMENT_CHANGED","REFUND_REJECTED:${current.id}")
            rejected
        }
    }
    fun list(status: String?,page: Int,size: Int): List<RefundRequest> { PaymentService.pagination(page,size); return repository.refunds(status,page*size,size) }
    fun recover() { repository.refundRecovery().forEach { r ->
        try { refresh(r) } catch(e: Exception) { org.slf4j.LoggerFactory.getLogger(javaClass).error("Refund recovery {} requires attention ({})",r.id,(e as? com.sagomungchi.core._common.exception.BusinessException)?.code ?: e.javaClass.simpleName) }
    } }
    fun refresh(refund: RefundRequest) {
        val payment=repository.paymentId(refund.paymentId) ?: missing()
        val order=repository.order(payment.orderId) ?: missing()
        val attempt=repository.latest(order.id) ?: missing()
        // Recovery never issues another cancellation or a new key after an ambiguous result.
        applyVerified(refund,pg.lookup(attempt.pgOrderNo,order.kind=="RENEWAL"))
    }
    fun refreshOwned(parent: UUID,no: String) {
        val order=tx.ownedOrder(parent,no)
        repository.pendingRefund(order.id)?.takeIf { it.status=="APPROVED" }?.let(::refresh)
    }
    fun applyVerified(refund: RefundRequest,result: PgResult) {
        val payment=repository.paymentId(refund.paymentId) ?: missing()
        val order=repository.order(payment.orderId) ?: missing()
        val attempt=repository.latest(order.id) ?: missing()
        if(result is PgResult.Found) payments.validate(order,attempt,result.payment)
        tx.locked(order.parentUserId) {
            val current=repository.refund(refund.id) ?: missing()
            if(current.status !in setOf("REQUESTED","APPROVED","FAILED")) return@locked Unit
            val p=repository.paymentId(payment.id) ?: missing()
            when {
                result is PgResult.Found && result.payment.status=="CANCELED" && result.payment.balanceAmount==0 -> {
                    check(repository.saveRefund(current.copy(status="COMPLETED",pgStatus="CANCELED"))==1)
                    check(repository.savePayment(p.copy(status="REFUNDED",canceledAt=tx.now(),entitlementStatus="APPLIED",updatedAt=tx.now()))==1)
                    order.subscriptionId?.let { repository.subscription(it)?.let { s -> repository.saveSubscription(tx.cancelSubscription(s)) } }
                    check(repository.finishAttempt(attempt.id,"CANCELED",null,null,tx.now())==1)
                    payments.notify(order,"PAYMENT_CHANGED","REFUNDED")
                    payments.notify(order,"SUBSCRIPTION_CHANGED","REFUNDED")
                }
                result is PgResult.Rejected && current.status=="APPROVED" -> {
                    check(repository.saveRefund(current.copy(status="FAILED",pgStatus=result.code))==1)
                    check(repository.savePayment(p.copy(status="APPROVED",updatedAt=tx.now()))==1)
                    payments.notify(order,"PAYMENT_CHANGED","REFUND_FAILED:${current.id}")
                }
                else -> Unit
            }
        }
    }
    private fun eligible(payment: Payment,requestedAt: java.time.OffsetDateTime=tx.now()) {
        val approved=payment.approvedAt ?: conflict("REFUND_NOT_ALLOWED")
        if(payment.status !in setOf("APPROVED","REFUND_REVIEW") || payment.entitlementStatus!="APPLIED" || requestedAt<approved ||
            Duration.between(approved,requestedAt)>Duration.ofDays(7)) conflict("REFUND_NOT_ALLOWED")
    }
    private fun localUnused(order: PaymentOrder,payment: Payment) {
        if(order.productSnapshot==null || repository.latest(order.id)==null) unavailable("REFUND_USAGE_UNAVAILABLE")
        if(repository.usageCount(order.studentId,requireNotNull(payment.approvedAt))>0) conflict("REFUND_PREMIUM_USAGE_PRESENT")
    }
}
