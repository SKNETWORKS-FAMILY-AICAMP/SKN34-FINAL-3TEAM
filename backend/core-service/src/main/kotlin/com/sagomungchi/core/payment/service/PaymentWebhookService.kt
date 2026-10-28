package com.sagomungchi.core.payment.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.payment.client.PgResult
import com.sagomungchi.core.payment.client.TossGateway
import com.sagomungchi.core.payment.repository.PaymentRepository
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.forbidden
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service
import java.security.MessageDigest
import java.util.Base64
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

@Service
class PaymentWebhookService(private val repository: PaymentRepository,private val tx: PaymentTransactions,
    private val pg: TossGateway,private val payments: PaymentService,private val refunds: RefundService,private val json: ObjectMapper,
    @Value("\${app.payment.webhook-security-key:}") private val securityKey: String,
    @Value("\${app.payment.billing-webhook-security-key:}") private val billingSecurityKey: String) {
    fun receive(raw: ByteArray,transmission: String,time: String,signature: String) {
        if(raw.size>32768 || transmission.length !in 1..200 || time.length !in 1..100 || signature.length>2000) forbidden()
        val configured=listOf(securityKey,billingSecurityKey).filter(String::isNotBlank).distinct()
        if(configured.isEmpty()) unavailable("PAYMENT_WEBHOOK_UNAVAILABLE")
        val valid=configured.any { key ->
            val mac=Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(key.toByteArray(),"HmacSHA256")) }
            mac.update(raw);val expected=mac.doFinal(":$time".toByteArray())
            signature.split(',').any { value -> value.trim().takeIf { it.startsWith("v1:") }?.removePrefix("v1:")?.let {
                runCatching { MessageDigest.isEqual(expected,Base64.getDecoder().decode(it)) }.getOrDefault(false)
            }==true }
        }
        if(!valid) forbidden()
        if(repository.webhookDone(transmission)) return
        val n=try { json.readTree(raw) } catch (_: Exception) { forbidden() }
        if(n.path("eventType").asText()!="PAYMENT_STATUS_CHANGED") forbidden()
        val no=n.path("data").path("orderId").asText()
        val attempt=repository.attemptNo(no) ?: forbidden()
        val order=repository.order(attempt.orderId) ?: forbidden()
        val result=pg.lookup(no,order.kind=="RENEWAL")
        if(result !is PgResult.Found) unavailable("PAYMENT_WEBHOOK_LOOKUP_UNAVAILABLE")
        val refund=repository.pendingRefund(order.id)
        if(refund!=null && result.payment.status=="CANCELED") refunds.applyVerified(refund,result) else payments.accept(order,attempt,result)
        // The transition is independently idempotent; crash before this receipt safely repeats PG lookup.
        tx.locked(order.parentUserId) { repository.webhook(UUID.randomUUID(),transmission,"PAYMENT_STATUS_CHANGED",no,tx.now()) }
    }
}
