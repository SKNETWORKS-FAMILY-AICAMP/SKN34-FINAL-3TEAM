package com.sagomungchi.core.payment.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.notification.service.NotificationService
import com.sagomungchi.core.payment.client.*
import com.sagomungchi.core.payment.domain.*
import com.sagomungchi.core.payment.repository.PaymentRepository
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.conflict
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.missing
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

data class OrderCreated(val orderId: String, val amount: Int, val orderName: String, val childId: UUID, val productId: UUID)
data class BillingSetup(val customerKey: String, val subscriptionId: UUID)

@Service
class PaymentService(private val repository: PaymentRepository, private val tx: PaymentTransactions,
    private val pg: TossGateway, private val cipher: BillingKeyCipher, private val notifications: NotificationService,
    @Value("\${app.payment.toss-mid:}") private val mid: String,
    @Value("\${app.payment.toss-billing-mid:}") private val billingMid: String) {
    fun products()=repository.products()
    fun create(parent: UUID, child: UUID, productId: UUID): OrderCreated = tx.locked(parent) {
        tx.students.requireLinked(parent,child)
        expireIfFinished(child)
        if(repository.active(child) != null || repository.confirmingStudent(child)) conflict("SUBSCRIPTION_DUPLICATE")
        val product=repository.product(productId)?.takeIf { it.active } ?: missing()
        if(product.price <= 0 || product.billingCycle != "MONTHLY" || product.childLimit != 1) conflict("PRODUCT_NOT_PURCHASABLE")
        if(!product.limits.path("dailyConversations").isIntegralNumber || !product.limits.path("dailyConversations").canConvertToInt() ||
            product.limits.path("dailyConversations").intValue()<0 || !product.limits.path("reportNarrative").isBoolean) conflict("PRODUCT_TERMS_INVALID")
        val id=UUID.randomUUID(); val order=PaymentOrder(id,"ord-$id",parent,child,product.id,null,"INITIAL",null,
            product.price,tx.json.valueToTree(product),tx.now())
        check(repository.insertOrder(order)==1)
        OrderCreated(order.orderNo,order.amount,product.name,child,product.id)
    }
    fun confirm(parent: UUID, orderNo: String, key: String, amount: Int): PaymentView {
        val prepared=tx.locked(parent) {
            val order=tx.ownedOrder(parent,orderNo)
            tx.students.requireLinked(parent,order.studentId)
            if(order.amount != amount) throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"PAYMENT_AMOUNT_MISMATCH","서버 주문 금액과 일치하지 않습니다.")
            if(order.kind != "INITIAL") conflict("PAYMENT_ORDER_KIND_MISMATCH")
            val existing=repository.latest(order.id)
            if(existing != null) {
                if(existing.paymentKey != key) conflict("PAYMENT_KEY_MISMATCH")
                order to null
            } else {
                expireIfFinished(order.studentId)
                if(repository.active(order.studentId)!=null || repository.confirmingStudent(order.studentId)) conflict("SUBSCRIPTION_DUPLICATE")
                val attempt=ChargeAttempt(UUID.randomUUID(),order.id,0,order.orderNo,UUID.randomUUID(),"CONFIRMING",key,null,tx.now(),tx.now())
                check(repository.insertAttempt(attempt)==1)
                check(repository.savePayment(Payment(UUID.randomUUID(),order.id,key,order.amount,"CONFIRMING",null,null,null,null,null,tx.now()))==1)
                order to attempt
            }
        }
        val (order,attempt)=prepared
        if(attempt != null) accept(order,attempt,pg.confirm(key,attempt.pgOrderNo,order.amount,attempt.idempotencyKey))
        else reconcile(order)
        return view(repository.order(order.id) ?: missing())
    }
    fun status(parent: UUID, no: String): PaymentView {
        val order=tx.ownedOrder(parent,no)
        reconcile(order)
        return view(repository.order(order.id) ?: missing())
    }
    fun list(parent: UUID?, status: String?, from: LocalDate?, to: LocalDate?, page: Int, size: Int): List<PaymentView> {
        pagination(page,size)
        if(from != null && to != null && from>to) conflict("INVALID_DATE_RANGE")
        return repository.orders(parent,status,from,to,page*size,size).map(::view)
    }
    fun subscriptions(parent: UUID)=repository.subscriptions(parent).map { it.view() }
    fun reconciliation(from: LocalDate?,to: LocalDate?,page: Int,size: Int): List<Map<String,Any?>> {
        pagination(page,size)
        if(from==null || to==null) conflict("PAYMENT_RECONCILIATION_RANGE_REQUIRED")
        if(from>to) conflict("INVALID_DATE_RANGE")
        val orders=mutableListOf<PaymentOrder>();var offset=0
        do {
            val batch=repository.orders(null,null,from,to,offset,100)
            orders.addAll(batch);offset+=batch.size
            if(batch.size<100) break
        } while(true)
        val rows=orders.map { order ->
            val attempt=repository.latest(order.id)
            val result=attempt?.let { pg.lookup(it.pgOrderNo,order.kind=="RENEWAL") }
            val local=repository.payment(order.id)
            val state=when(result) {
                null -> "NO_PG_ATTEMPT"
                PgResult.Missing -> "MISSING_PG"
                is PgResult.Found -> {
                    val valid=runCatching { validate(order,requireNotNull(attempt),result.payment) }.isSuccess &&
                        (local?.paymentKey==null || local.paymentKey==result.payment.paymentKey)
                    val expected=when(local?.status) { "APPROVED","REFUND_REVIEW" -> "DONE"; "REFUNDED","CANCELED" -> "CANCELED"; else -> null }
                    if(valid && expected==result.payment.status) "MATCH" else "MISMATCH"
                }
                else -> "UNKNOWN"
            }
            mapOf("orderId" to order.orderNo,"localStatus" to local?.status,"pgStatus" to (result as? PgResult.Found)?.payment?.status,
                "result" to state,"entitlementStatus" to local?.entitlementStatus,"source" to "LOCAL")
        }.toMutableList()
        val seen=mutableSetOf<String>()
        for(billing in listOf(false,true)) {
            val expected=if(billing) billingMid else mid
            if(expected.isBlank()) unavailable("PAYMENT_PG_UNAVAILABLE")
            val transactions=pg.transactions(from,to,billing) ?: unavailable("PAYMENT_RECONCILIATION_UNAVAILABLE")
            transactions.forEach { item ->
                if(item.mid!=expected) unavailable("PAYMENT_PG_MISMATCH")
                if(!seen.add(item.mid+":"+item.transactionKey)) return@forEach
                val attempt=repository.attemptNo(item.orderId)
                val order=attempt?.let { repository.order(it.orderId) }
                val local=order?.let { repository.payment(it.id) }
                val state=when {
                    order==null -> "MISSING_LOCAL"
                    item.status=="DONE" && item.amount!=order.amount -> "MISMATCH"
                    item.status=="DONE" && local?.paymentKey!=null && local.paymentKey!=item.paymentKey -> {
                        val current=pg.lookup(item.orderId,billing)
                        if(current is PgResult.Found && current.payment.status=="DONE" && current.payment.paymentKey==item.paymentKey &&
                            current.payment.mid==expected && current.payment.amount==order.amount) "DUPLICATE" else "MISMATCH"
                    }
                    else -> "MATCH"
                }
                rows+=mapOf("orderId" to (order?.orderNo ?: item.orderId),"localStatus" to local?.status,"pgStatus" to item.status,
                    "result" to state,"entitlementStatus" to local?.entitlementStatus,"source" to "PG")
            }
        }
        return rows.sortedWith(compareBy({it["orderId"].toString()},{it["source"].toString()},{it["result"].toString()})).drop(page*size).take(size)
    }
    fun view(order: PaymentOrder): PaymentView {
        val payment=repository.payment(order.id)
        return PaymentView(payment?.id,order.orderNo,order.studentId,order.amount,payment?.status ?: "PENDING",payment?.entitlementStatus,
            payment?.approvedAt,payment?.failureCode,order.subscriptionId?.let { repository.subscription(it)?.view() },repository.refundHistory(order.id))
    }
    fun reconcile(order: PaymentOrder) {
        val payment=repository.payment(order.id) ?: return
        val attempt=repository.latest(order.id) ?: return
        if(payment.status=="CONFIRMING") accept(order,attempt,pg.lookup(attempt.pgOrderNo,order.kind=="RENEWAL"))
        if(repository.payment(order.id)?.entitlementStatus=="RECOVERY_REQUIRED") recover(order)
    }
    fun accept(order: PaymentOrder, attempt: ChargeAttempt, result: PgResult) {
        if(result is PgResult.Found) validate(order,attempt,result.payment)
        tx.locked(order.parentUserId) {
            val latest=repository.latest(order.id) ?: missing()
            if(latest.id != attempt.id) return@locked Unit
            val payment=repository.payment(order.id) ?: missing()
            if(payment.status in setOf("REFUNDED","CANCELED","REFUND_REVIEW") || latest.status=="FAILED") return@locked Unit
            when(result) {
                is PgResult.Found -> when(result.payment.status) {
                    "DONE" -> {
                        if(payment.status!="APPROVED") {
                            check(repository.finishAttempt(attempt.id,"APPROVED",result.payment.paymentKey,null,tx.now())==1)
                            check(repository.savePayment(payment.copy(paymentKey=result.payment.paymentKey,status="APPROVED",method=result.payment.method,
                                approvedAt=result.payment.approvedAt,entitlementStatus="RECOVERY_REQUIRED",failureCode=null,updatedAt=tx.now()))==1)
                            notify(order,"PAYMENT_CHANGED","APPROVED")
                        }
                    }
                    "ABORTED","EXPIRED" -> fail(order,attempt,payment,"PG_${result.payment.status}")
                    "CANCELED" -> {
                        check(result.payment.balanceAmount==0)
                        check(repository.finishAttempt(attempt.id,"CANCELED",result.payment.paymentKey,null,tx.now())==1)
                        val canceled=if(payment.approvedAt!=null || result.payment.approvedAt!=null) "REFUNDED" else "CANCELED"
                        check(repository.savePayment(payment.copy(status=canceled,entitlementStatus=null,canceledAt=tx.now(),updatedAt=tx.now()))==1)
                        order.subscriptionId?.let { repository.subscription(it)?.let { s -> repository.saveSubscription(tx.cancelSubscription(s)) } }
                        notify(order,"PAYMENT_CHANGED","CANCELED")
                    }
                    else -> Unit
                }
                is PgResult.Rejected -> if(payment.status=="CONFIRMING") fail(order,attempt,payment,result.code)
                else -> Unit // Missing, transport errors, ambiguous responses remain CONFIRMING.
            }
        }
        if(repository.payment(order.id)?.entitlementStatus=="RECOVERY_REQUIRED") recover(order)
    }
    private fun fail(order: PaymentOrder, attempt: ChargeAttempt, payment: Payment, code: String) {
        if(payment.status!="CONFIRMING") return
        check(repository.finishAttempt(attempt.id,"FAILED",null,code,tx.now())==1)
        check(repository.savePayment(payment.copy(status="FAILED",failureCode=code,updatedAt=tx.now()))==1)
        if(order.kind=="RENEWAL") {
            val s=repository.subscription(requireNotNull(order.subscriptionId)) ?: missing()
            val failed=s.copy(status="RENEWAL_FAILED",graceUntil=s.graceUntil ?: tx.today().plusDays(3),
                renewalRetryCount=attempt.attemptNo,nextBillingDate=tx.today().plusDays(1),updatedAt=tx.now())
            repository.saveSubscription(if(attempt.attemptNo>=3) tx.cancelSubscription(failed) else failed)
            notify(order,"SUBSCRIPTION_CHANGED","FAILED-${attempt.attemptNo}")
        }
        notify(order,"PAYMENT_CHANGED","FAILED-${attempt.attemptNo}")
    }
    fun validate(order: PaymentOrder, attempt: ChargeAttempt, payment: PgPayment) {
        val expected=if(order.kind=="RENEWAL") billingMid else mid
        if(expected.isBlank() || payment.mid!=expected || payment.currency!="KRW" || payment.orderId!=attempt.pgOrderNo || payment.amount!=order.amount ||
            (attempt.paymentKey!=null && attempt.paymentKey!=payment.paymentKey) ||
            (payment.status=="DONE" && (payment.approvedAt==null || payment.balanceAmount!=order.amount)))
            unavailable("PAYMENT_PG_MISMATCH")
    }
    fun recover(order: PaymentOrder) = tx.locked(order.parentUserId) {
        val current=repository.order(order.id) ?: missing()
        val p=repository.payment(order.id) ?: missing()
        if(p.status!="APPROVED" || p.entitlementStatus!="RECOVERY_REQUIRED") return@locked Unit
        tx.students.requireLinked(order.parentUserId,order.studentId)
        val approved=requireNotNull(p.approvedAt).atZoneSameInstant(ZoneId.of("Asia/Seoul")).toLocalDate()
        if(current.kind=="INITIAL") {
            current.subscriptionId?.let { repository.subscription(it) } ?: run {
                if(repository.active(current.studentId)!=null) conflict("SUBSCRIPTION_DUPLICATE")
                val s=Subscription(UUID.randomUUID(),current.parentUserId,current.studentId,current.productId,"ACTIVE",approved,
                    BillingDates.next(approved,approved.dayOfMonth),null,false,UUID.randomUUID().toString(),null,0,null,null,null,
                    tx.now(),tx.now(),current.productSnapshot,approved.dayOfMonth,null)
                check(repository.insertSubscription(s)==1); check(repository.attach(current.id,s.id)==1); s
            }
        } else {
            val s=repository.subscription(requireNotNull(current.subscriptionId)) ?: missing()
            // Preserve a cancellation made while the external charge was in flight.
            val start=requireNotNull(current.billingPeriodStart); val end=BillingDates.next(start,requireNotNull(s.billingAnchorDay))
            val renewed=s.copy(status="ACTIVE",periodStart=start,periodEnd=end,nextBillingDate=if(s.autoRenew) end else null,
                graceUntil=null,renewalRetryCount=0,canceledAt=null,updatedAt=tx.now())
            check(repository.saveSubscription(renewed)==1); renewed
        }
        check(repository.savePayment(p.copy(entitlementStatus="APPLIED",updatedAt=tx.now()))==1)
        notifications.payment(order.parentUserId,order.studentId,event("${order.id}:ENTITLED"),true,"구독 이용 권한이 반영되었습니다.")
    }
    fun billingSetup(parent: UUID, id: UUID): BillingSetup = tx.locked(parent) {
        val s=tx.ownedSubscription(parent,id)
        if(s.status !in setOf("ACTIVE","RENEWAL_FAILED") || !BillingDates.entitled(s,tx.now()) || repository.refundPending(s.studentId)) conflict("SUBSCRIPTION_NOT_ACTIVE")
        BillingSetup(s.customerKey ?: unavailable("PAYMENT_CUSTOMER_UNAVAILABLE"),s.id)
    }
    fun billing(parent: UUID, id: UUID, authKey: String, customer: String, key: UUID): SubscriptionView {
        val original=tx.locked(parent) {
            val s=tx.ownedSubscription(parent,id); tx.students.requireLinked(parent,s.studentId)
            if(s.status !in setOf("ACTIVE","RENEWAL_FAILED") || !BillingDates.entitled(s,tx.now()) || s.customerKey!=customer || repository.refundPending(s.studentId)) conflict("SUBSCRIPTION_NOT_ACTIVE")
            s
        }
        // Validate encryption configuration before a one-time authKey is consumed.
        cipher.encrypt("configuration-check")
        val issued=pg.issue(authKey,customer,key)
        val encrypted=cipher.encrypt(issued.billingKey)
        return tx.locked(parent) {
            val s=tx.ownedSubscription(parent,id)
            if(s.revision!=original.revision || s.status !in setOf("ACTIVE","RENEWAL_FAILED") || !BillingDates.entitled(s,tx.now()) || repository.refundPending(s.studentId)) conflict("SUBSCRIPTION_STATE_CHANGED")
            val retryDate=if(tx.now().atZoneSameInstant(ZoneId.of("Asia/Seoul")).toLocalTime()<java.time.LocalTime.of(9,0) && s.lastBillingAttemptDate!=tx.today()) tx.today() else tx.today().plusDays(1)
            val next=if(s.status=="ACTIVE") s.periodEnd else maxOf(s.nextBillingDate ?: retryDate,retryDate)
            val changed=s.copy(billingKeyEnc=encrypted,autoRenew=true,nextBillingDate=next,autoRenewCanceledAt=null,updatedAt=tx.now())
            check(repository.saveSubscription(changed)==1)
            notifications.payment(parent,s.studentId,event("$id:BILLING:$key"),true,"자동결제 수단이 등록되었습니다.")
            changed.view()
        }
    }
    fun autoRenew(parent: UUID, id: UUID, enabled: Boolean): SubscriptionView = tx.locked(parent) {
        val s=tx.ownedSubscription(parent,id)
        if(!enabled && s.status=="CANCELED") return@locked s.view()
        if(s.status !in setOf("ACTIVE","RENEWAL_FAILED")) conflict("SUBSCRIPTION_NOT_ACTIVE")
        if(enabled) {
            tx.students.requireLinked(parent,s.studentId)
            if(s.status!="ACTIVE" || !BillingDates.entitled(s,tx.now()) || repository.refundPending(s.studentId)) conflict("SUBSCRIPTION_NOT_ACTIVE")
        }
        if(enabled && s.billingKeyEnc==null) conflict("BILLING_KEY_REQUIRED")
        if(!enabled && !BillingDates.entitled(s,tx.now()) && !repository.confirmingStudent(s.studentId)) {
            val canceled=tx.cancelSubscription(s.copy(autoRenewCanceledAt=tx.now()))
            check(repository.saveSubscription(canceled)==1);subscriptionCanceled(s);return@locked canceled.view()
        }
        if(s.autoRenew==enabled) {
            if(!enabled) check(repository.saveSubscription(s.copy(autoRenewCanceledAt=tx.now(),updatedAt=tx.now()))==1)
            return@locked s.view()
        }
        val changed=s.copy(autoRenew=enabled,nextBillingDate=if(enabled) s.periodEnd else null,
            autoRenewCanceledAt=if(enabled) null else tx.now(),updatedAt=tx.now())
        check(repository.saveSubscription(changed)==1)
        notifications.payment(parent,s.studentId,UUID.randomUUID(),true,if(enabled) "자동 갱신 해지가 철회되었습니다." else "이용 기간 종료 후 자동 갱신하지 않습니다.")
        changed.view()
    }
    private fun expireIfFinished(student: UUID) {
        val s=repository.active(student) ?: return
        if(!s.autoRenew && !BillingDates.entitled(s,tx.now()) && !repository.confirmingStudent(student)) {
            check(repository.saveSubscription(tx.cancelSubscription(s))==1);subscriptionCanceled(s)
        }
    }
    fun subscriptionCanceled(s: Subscription)=notifications.payment(s.parentUserId,s.studentId,event("${s.id}:EXPIRED:${s.periodEnd}"),true,"구독 이용 기간이 종료되었습니다.")
    fun notify(order: PaymentOrder, type: String, state: String) = notifications.payment(order.parentUserId,order.studentId,
        event("${order.id}:$type:$state"),type=="SUBSCRIPTION_CHANGED",if(type=="SUBSCRIPTION_CHANGED") "구독 상태가 변경되었습니다." else "결제 상태가 변경되었습니다.")
    companion object {
        fun event(value: String): UUID=UUID.nameUUIDFromBytes(value.toByteArray())
        fun pagination(page: Int,size: Int) { if(page !in 0..10000 || size !in 1..100) conflict("INVALID_PAGE") }
    }
}
