package com.sagomungchi.core.payment.controller

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.payment.service.*
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.forbidden
import jakarta.servlet.http.HttpServletRequest
import jakarta.validation.Valid
import jakarta.validation.constraints.*
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.time.LocalDate
import java.util.UUID

data class CreateOrderRequest(val productId: UUID,val childId: UUID)
// Not data classes: one-time PG tokens must never appear in toString().
class ConfirmPaymentRequest(@field:NotBlank @field:Size(max=200) val paymentKey: String,
    @field:Pattern(regexp="[A-Za-z0-9_-]{6,64}") val orderId: String,@field:Positive val amount: Int)
class RegisterBillingRequest(@field:NotBlank @field:Size(max=300) val authKey: String,
    @field:NotBlank @field:Size(min=10,max=50) val customerKey: String)
data class RefundReason(@field:NotBlank @field:Size(max=200) val reason: String)

@RestController
class PaymentController(private val payments: PaymentService,private val refunds: RefundService,
    private val webhook: PaymentWebhookService,private val idempotency: IdempotencyService,private val json: ObjectMapper) {
    @ModelAttribute fun noStore(response: jakarta.servlet.http.HttpServletResponse) { response.setHeader("Cache-Control","no-store") }
    @ExceptionHandler(org.springframework.dao.DataAccessException::class)
    fun storageUnavailable(request: HttpServletRequest)=com.sagomungchi.core._common.exception.Problems.of(
        org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,"PAYMENT_STORAGE_UNAVAILABLE","거래 저장 결과를 확인하지 못했습니다. 같은 거래로 상태를 조회해 주세요.",null,request)
    @GetMapping("/api/v1/products") fun products()=mapOf("items" to payments.products())
    @PostMapping("/api/v1/orders")
    fun order(@Valid @RequestBody body: CreateOrderRequest,@RequestHeader("Idempotency-Key") key: UUID,request: HttpServletRequest)=
        cached(request,key,"POST /orders",body,201) { payments.create(parent(request),body.childId,body.productId) }
    @PostMapping("/api/v1/payments/confirm")
    fun confirm(@Valid @RequestBody body: ConfirmPaymentRequest,@RequestHeader("Idempotency-Key") key: UUID,request: HttpServletRequest)=
        cached(request,key,"POST /payments/confirm",body) { PaymentViewResponse.from(payments.confirm(parent(request),body.orderId,body.paymentKey,body.amount)) }
    @GetMapping("/api/v1/payments/{orderId}")
    fun status(@PathVariable orderId: String,request: HttpServletRequest): PaymentViewResponse {
        val user=parent(request);refunds.refreshOwned(user,orderId);return PaymentViewResponse.from(payments.status(user,orderId))
    }
    @GetMapping("/api/v1/payments")
    fun list(request: HttpServletRequest,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=
        mapOf("items" to payments.list(parent(request),null,null,null,page,size).map(PaymentViewResponse::from))
    @GetMapping("/api/v1/subscriptions") fun subscriptions(request: HttpServletRequest)=mapOf("items" to payments.subscriptions(parent(request)))
    @GetMapping("/api/v1/subscriptions/{subscriptionId}/billing-key")
    fun setup(@PathVariable subscriptionId: UUID,request: HttpServletRequest)=payments.billingSetup(parent(request),subscriptionId)
    @PostMapping("/api/v1/subscriptions/{subscriptionId}/billing-key")
    fun billing(@PathVariable subscriptionId: UUID,@Valid @RequestBody body: RegisterBillingRequest,
        @RequestHeader("Idempotency-Key") key: UUID,request: HttpServletRequest)=
        cached(request,key,"POST /subscriptions/$subscriptionId/billing-key",body) { payments.billing(parent(request),subscriptionId,body.authKey,body.customerKey,key) }
    @DeleteMapping("/api/v1/subscriptions/{subscriptionId}/auto-renewal")
    fun cancel(@PathVariable subscriptionId: UUID,request: HttpServletRequest)=payments.autoRenew(parent(request),subscriptionId,false)
    @PutMapping("/api/v1/subscriptions/{subscriptionId}/auto-renewal")
    fun resume(@PathVariable subscriptionId: UUID,request: HttpServletRequest)=payments.autoRenew(parent(request),subscriptionId,true)
    @PostMapping("/api/v1/payments/{paymentId}/refund-requests")
    fun refund(@PathVariable paymentId: UUID,@Valid @RequestBody body: RefundReason,@RequestHeader("Idempotency-Key") key: UUID,request: HttpServletRequest)=
        cached(request,key,"POST /payments/$paymentId/refund-requests",body,201) { RefundRequestResponse.from(refunds.request(parent(request),paymentId,body.reason)) }
    @GetMapping("/api/v1/admin/payments")
    fun adminPayments(request: HttpServletRequest,@RequestParam(required=false) status: String?,@RequestParam(required=false) from: LocalDate?,
        @RequestParam(required=false) to: LocalDate?,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int): Any {
        admin(request,"PAYMENT_VIEW"); return mapOf("items" to payments.list(null,status,from,to,page,size).map(PaymentViewResponse::from))
    }
    @GetMapping("/api/v1/admin/payments/reconciliation")
    fun reconciliation(request: HttpServletRequest,@RequestParam(required=false) from: LocalDate?,@RequestParam(required=false) to: LocalDate?,
        @RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int): Any {
        admin(request,"PAYMENT_VIEW"); return mapOf("items" to payments.reconciliation(from,to,page,size))
    }
    @GetMapping("/api/v1/admin/refund-requests")
    fun adminRefunds(request: HttpServletRequest,@RequestParam(required=false) status: String?,@RequestParam(defaultValue="0") page: Int,
        @RequestParam(defaultValue="20") size: Int): Any { admin(request,"PAYMENT_VIEW"); return mapOf("items" to refunds.list(status,page,size).map(RefundRequestResponse::from)) }
    @PostMapping("/api/v1/admin/refund-requests/{requestId}/approve")
    fun approve(@PathVariable requestId: UUID,@RequestHeader("Idempotency-Key") key: UUID,request: HttpServletRequest)=
        cached(request,key,"POST /admin/refund-requests/$requestId/approve",mapOf("id" to requestId)) { RefundRequestResponse.from(refunds.approve(admin(request,"PAYMENT_REFUND"),requestId)) }
    @PostMapping("/api/v1/admin/refund-requests/{requestId}/reject")
    fun reject(@PathVariable requestId: UUID,@Valid @RequestBody body: RefundReason,request: HttpServletRequest)=RefundRequestResponse.from(refunds.reject(admin(request,"PAYMENT_REFUND"),requestId,body.reason))
    @PostMapping("/api/v1/webhooks/tosspayments")
    fun webhook(@RequestBody raw: ByteArray,@RequestHeader("tosspayments-webhook-transmission-id") id: String,
        @RequestHeader("tosspayments-webhook-transmission-time") time: String,@RequestHeader("tosspayments-webhook-signature") signature: String): Map<String,Boolean> {
        webhook.receive(raw,id,time,signature); return mapOf("received" to true)
    }
    private fun parent(r: HttpServletRequest): UUID=identity(r).also { if(it.session.role!="PARENT") forbidden() }.account.id
    private fun admin(r: HttpServletRequest,permission: String): UUID=identity(r).also { if(it.session.role!="ADMIN" || permission !in it.permissions) forbidden() }.account.id
    private fun identity(r: HttpServletRequest)=r.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
    private fun cached(request: HttpServletRequest,key: UUID,endpoint: String,body: Any,status: Int=200,operation: ()->Any): ResponseEntity<ByteArray> {
        val identity=identity(request)
        val result=idempotency.execute(key,identity.account.id,endpoint,identity.studentScope.map(UUID::toString).toSet(),json.writeValueAsBytes(body)) {
          try {
            val value=operation()
            val actual=when { value is PaymentViewResponse && value.status=="CONFIRMING" -> 202
                value is RefundRequestResponse && value.status=="APPROVED" -> 202
                else -> status }
            HttpExchangeResult(actual,mapOf("Content-Type" to listOf("application/json"),"Cache-Control" to listOf("no-store")),json.writeValueAsBytes(value))
          } catch(e: com.sagomungchi.core._common.exception.BusinessException) {
            HttpExchangeResult(e.status.value(),mapOf("Content-Type" to listOf("application/problem+json"),"Cache-Control" to listOf("no-store")),
                json.writeValueAsBytes(com.sagomungchi.core._common.exception.Problems.of(e.status,e.code,e.title,e.detail,request)))
          }
        }
        val response=ResponseEntity.status(result.status)
        result.headers.forEach { (name,values)->response.header(name,*values.toTypedArray()) }
        return response.body(result.body)
    }
}

@RestController
class InternalPaymentUsageController(private val products: ProductEntitlementService) {
    data class Start(val studentId: UUID,val sourceId: UUID)
    data class Finish(val studentId: UUID,val reservationId: UUID,val used: Boolean)
    @PostMapping("/internal/payment-usage/reservations") fun begin(@RequestBody body: Start): UsagePermit {
        scope(body.studentId); return products.beginFeedback(body.studentId,body.sourceId)
    }
    @PostMapping("/internal/payment-usage/completions") fun complete(@RequestBody body: Finish): Map<String,Boolean> {
        scope(body.studentId); products.finishUsage(body.studentId,body.reservationId,body.used); return mapOf("received" to true)
    }
    private fun scope(student: UUID) {
        val context=UserContextHolder.currentOrNull() ?: forbidden()
        if(context.role!="STUDENT") forbidden()
        context.requireStudent(student.toString())
    }
}
