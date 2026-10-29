package com.sagomungchi.core.payment.domain

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.annotation.JsonIgnore
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID

data class Product(val id: UUID, val code: String, val name: String, val price: Int, val billingCycle: String,
    val childLimit: Int, val features: JsonNode, val limits: JsonNode, val active: Boolean)

data class PaymentOrder(val id: UUID, val orderNo: String, val parentUserId: UUID, val studentId: UUID,
    val productId: UUID, val subscriptionId: UUID?, val kind: String, val billingPeriodStart: LocalDate?,
    val amount: Int, val productSnapshot: JsonNode?, val createdAt: OffsetDateTime)

data class Payment(val id: UUID, val orderId: UUID, @get:JsonIgnore val paymentKey: String?, val amount: Int,
    val status: String, val method: String?, val entitlementStatus: String?, val failureCode: String?,
    val approvedAt: OffsetDateTime?, val canceledAt: OffsetDateTime?, val updatedAt: OffsetDateTime)

// Never serialize or log persistence objects with payment credentials.
class ChargeAttempt(val id: UUID, val orderId: UUID, val attemptNo: Int, val pgOrderNo: String,
    val idempotencyKey: UUID, val status: String, val paymentKey: String?, val failureCode: String?,
    val startedAt: OffsetDateTime, val updatedAt: OffsetDateTime)

data class Subscription(val id: UUID, val parentUserId: UUID, val studentId: UUID, val productId: UUID,
    val status: String, val periodStart: LocalDate, val periodEnd: LocalDate, val nextBillingDate: LocalDate?,
    val autoRenew: Boolean, val customerKey: String?, val billingKeyEnc: String?, val renewalRetryCount: Int?,
    val graceUntil: LocalDate?, val autoRenewCanceledAt: OffsetDateTime?, val canceledAt: OffsetDateTime?,
    val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime, val productSnapshot: JsonNode?,
    val billingAnchorDay: Int?, val lastBillingAttemptDate: LocalDate?,val revision: Long=0) {
    override fun toString() = "Subscription(id=$id,status=$status)"
}

data class RefundRequest(val id: UUID, val paymentId: UUID, val requestedBy: UUID, val amount: Int,
    val reason: String, val status: String, val decidedBy: UUID?, val rejectReason: String?, val pgStatus: String?,
    val decidedAt: OffsetDateTime?, val createdAt: OffsetDateTime, @get:JsonIgnore val cancelKey: UUID?, val usageVerifiedAt: OffsetDateTime?)

data class PremiumUsage(val id: UUID, val studentId: UUID, val subscriptionId: UUID, val kind: String,
    val sourceId: UUID, val status: String, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)

data class SubscriptionView(val subscriptionId: UUID, val childId: UUID, val product: JsonNode?, val status: String,
    val periodStart: LocalDate, val periodEnd: LocalDate, val nextBillingDate: LocalDate?, val autoRenew: Boolean,
    val graceUntil: LocalDate?, val renewalRetryCount: Int, val billingRegistered: Boolean)
fun Subscription.view() = SubscriptionView(id,studentId,productSnapshot,status,periodStart,periodEnd,nextBillingDate,
    autoRenew,graceUntil,renewalRetryCount ?: 0,billingKeyEnc != null)

data class PaymentView(val paymentId: UUID?, val orderId: String, val childId: UUID, val amount: Int,
    val status: String, val entitlementStatus: String?, val approvedAt: OffsetDateTime?, val failureCode: String?,
    val subscription: SubscriptionView?,val refundRequests: List<RefundRequest> = emptyList())

data class ProductEntitlement(val childId: UUID, val product: Product, val subscriptionId: UUID?,
    val status: String, val autoRenew: Boolean, val periodEnd: LocalDate?, val graceUntil: LocalDate?,
    val refundPending: Boolean, val conversationEnabled: Boolean, val narrativeEnabled: Boolean)

object BillingDates {
    fun next(start: LocalDate, anchor: Int): LocalDate {
        val month = start.plusMonths(1).withDayOfMonth(1)
        return month.withDayOfMonth(minOf(anchor,month.lengthOfMonth()))
    }
    fun entitled(s: Subscription, now: OffsetDateTime) = when(s.status) {
        "ACTIVE" -> now.toInstant() < s.periodEnd.atTime(9,0).atZone(ZoneId.of("Asia/Seoul")).toInstant()
        "RENEWAL_FAILED" -> s.graceUntil?.let { now.toInstant() <= it.atTime(9,0).atZone(ZoneId.of("Asia/Seoul")).toInstant() } == true
        else -> false
    }
}
