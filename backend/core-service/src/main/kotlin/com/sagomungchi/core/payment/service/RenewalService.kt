package com.sagomungchi.core.payment.service

import com.sagomungchi.core.payment.client.TossGateway
import com.sagomungchi.core.payment.domain.*
import com.sagomungchi.core.payment.repository.PaymentRepository
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.conflict
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.missing
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class RenewalService(private val repository: PaymentRepository, private val tx: PaymentTransactions,
    private val payments: PaymentService, private val pg: TossGateway, private val cipher: BillingKeyCipher) {
    private val log=org.slf4j.LoggerFactory.getLogger(javaClass)
    fun due() { repository.due(tx.today()).forEach { s ->
        try { charge(s.id) } catch(e: Exception) { log.error("Payment renewal {} requires attention ({})",s.id,(e as? com.sagomungchi.core._common.exception.BusinessException)?.code ?: e.javaClass.simpleName) }
    } }
    fun recover() { repository.recovery().forEach { order ->
        try { payments.reconcile(order) } catch(e: Exception) { log.error("Payment recovery {} requires attention ({})",order.id,(e as? com.sagomungchi.core._common.exception.BusinessException)?.code ?: e.javaClass.simpleName) }
    } }
    fun charge(id: UUID) {
        val initial=repository.subscription(id) ?: return
        val prepared=tx.locked(initial.parentUserId) {
            val sub=repository.subscription(id) ?: missing()
            if(sub.status=="CANCELED" || sub.periodEnd>tx.today()) return@locked nullResult()
            if(repository.refundPending(sub.studentId)) return@locked nullResult()
            // In-flight/unknown PG transactions must resolve before cancellation or another attempt.
            val existing=repository.renewal(sub.id,sub.periodEnd)
            val last=existing?.let { repository.latest(it.id) }
            if(last?.status=="CONFIRMING" || existing?.let { repository.payment(it.id)?.entitlementStatus }=="RECOVERY_REQUIRED")
                return@locked Prepared(existing!!,last,null)
            if(!sub.autoRenew && sub.status=="RENEWAL_FAILED" && BillingDates.entitled(sub,tx.now())) return@locked nullResult()
            if(!sub.autoRenew || (sub.graceUntil!=null && tx.today()>sub.graceUntil) || (sub.renewalRetryCount ?: 0)>=3) {
                check(repository.saveSubscription(tx.cancelSubscription(sub))==1);payments.subscriptionCanceled(sub);return@locked nullResult()
            }
            if(sub.lastBillingAttemptDate?.let { it>=tx.today() }==true) return@locked nullResult()
            if(sub.nextBillingDate?.let { it>tx.today() }==true) return@locked nullResult()
            tx.students.requireLinked(sub.parentUserId,sub.studentId)
            if(sub.productSnapshot==null || sub.billingAnchorDay==null || sub.billingKeyEnc==null || sub.customerKey==null)
                unavailable("PAYMENT_RENEWAL_DATA_UNAVAILABLE")
            if(last!=null && last.status!="FAILED") return@locked nullResult()
            val order=existing ?: PaymentOrder(UUID.randomUUID(),"renew-${UUID.randomUUID()}",sub.parentUserId,sub.studentId,
                sub.productId,sub.id,"RENEWAL",sub.periodEnd,((sub.productSnapshot["price"] as? Number)?.toInt() ?: 0),sub.productSnapshot,tx.now()).also {
                    if(it.amount<=0) conflict("PAYMENT_PRODUCT_UNAVAILABLE")
                    check(repository.insertOrder(it)==1)
                }
            val attempt=ChargeAttempt(UUID.randomUUID(),order.id,(last?.attemptNo ?: -1)+1,"renew-${UUID.randomUUID()}",
                UUID.randomUUID(),"CONFIRMING",null,null,tx.now(),tx.now())
            check(repository.insertAttempt(attempt)==1)
            val p=repository.payment(order.id)
            check(repository.savePayment(Payment(p?.id ?: UUID.randomUUID(),order.id,null,order.amount,"CONFIRMING",null,null,null,null,null,tx.now()))==1)
            check(repository.saveSubscription(sub.copy(lastBillingAttemptDate=tx.today(),updatedAt=tx.now()))==1)
            Prepared(order,attempt,sub)
        }
        val order=prepared.order ?: return
        val attempt=prepared.attempt ?: return
        val sub=prepared.subscription
        if(sub==null) { payments.reconcile(order); return }
        val result=pg.charge(cipher.decrypt(requireNotNull(sub.billingKeyEnc)),requireNotNull(sub.customerKey),attempt.pgOrderNo,
            order.amount,tx.product(order).name,attempt.idempotencyKey)
        payments.accept(order,attempt,result)
    }
    private data class Prepared(val order: PaymentOrder?, val attempt: ChargeAttempt?, val subscription: Subscription?)
    private fun nullResult()=Prepared(null,null,null)
}
