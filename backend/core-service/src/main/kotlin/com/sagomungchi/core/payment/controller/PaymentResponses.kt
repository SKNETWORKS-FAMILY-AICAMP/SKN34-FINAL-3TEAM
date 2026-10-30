package com.sagomungchi.core.payment.controller

import com.sagomungchi.core.payment.domain.PaymentView
import com.sagomungchi.core.payment.domain.RefundRequest
import com.sagomungchi.core.payment.domain.SubscriptionView
import java.time.OffsetDateTime
import java.util.UUID

/** 환불 요청 응답 (api-spec 2.6, 관리자 목록·승인·반려 2.8). PG 취소 키(cancelKey)는 응답·멱등 저장본에 넣지 않음 (#168) */
data class RefundRequestResponse(val id: UUID, val paymentId: UUID, val requestedBy: UUID, val amount: Int,
    val reason: String, val status: String, val decidedBy: UUID?, val rejectReason: String?, val pgStatus: String?,
    val decidedAt: OffsetDateTime?, val createdAt: OffsetDateTime, val usageVerifiedAt: OffsetDateTime?) {
    companion object {
        fun from(r: RefundRequest) = RefundRequestResponse(r.id,r.paymentId,r.requestedBy,r.amount,r.reason,r.status,
            r.decidedBy,r.rejectReason,r.pgStatus,r.decidedAt,r.createdAt,r.usageVerifiedAt)
    }
}

/** 결제 응답 (api-spec 2.6). 결제 키는 PaymentView에도 없음, 환불 요청은 RefundRequestResponse로 */
data class PaymentViewResponse(val paymentId: UUID?, val orderId: String, val childId: UUID, val amount: Int,
    val status: String, val entitlementStatus: String?, val approvedAt: OffsetDateTime?, val failureCode: String?,
    val subscription: SubscriptionView?, val refundRequests: List<RefundRequestResponse>) {
    companion object {
        fun from(v: PaymentView) = PaymentViewResponse(v.paymentId,v.orderId,v.childId,v.amount,v.status,v.entitlementStatus,
            v.approvedAt,v.failureCode,v.subscription,v.refundRequests.map(RefundRequestResponse::from))
    }
}
