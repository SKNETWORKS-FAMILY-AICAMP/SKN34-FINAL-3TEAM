package com.sagomungchi.core.payment.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronizationManager
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
import org.springframework.beans.factory.annotation.Autowired
import java.net.URI
import java.net.URLEncoder
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
import java.time.Duration
import java.time.OffsetDateTime
import java.time.LocalDate
import java.util.Base64
import java.util.UUID

// Deliberately not data classes: credentials must not appear through toString().
class PgPayment(val orderId: String, val paymentKey: String, val amount: Int, val status: String,
    val mid: String, val approvedAt: OffsetDateTime?, val balanceAmount: Int, val method: String?,val currency: String="KRW")
class PgBilling(val billingKey: String, val customerKey: String)
class PgTransaction(val transactionKey: String,val orderId: String,val paymentKey: String,val mid: String,val amount: Int,val status: String)
sealed interface PgResult {
    class Found(val payment: PgPayment): PgResult
    class Rejected(val code: String): PgResult
    data object Unknown: PgResult
    data object Missing: PgResult
}

interface TossGateway {
    fun confirm(key: String, order: String, amount: Int, idempotency: UUID): PgResult
    fun lookup(order: String, billing: Boolean): PgResult
    fun charge(billingKey: String, customer: String, order: String, amount: Int, name: String, idempotency: UUID): PgResult
    fun cancel(paymentKey: String, amount: Int, billing: Boolean, idempotency: UUID): PgResult
    fun issue(authKey: String, customer: String, idempotency: UUID): PgBilling
    fun transactions(from: LocalDate,to: LocalDate,billing: Boolean): List<PgTransaction>?
}

@Component
class TossClient internal constructor(private val json: ObjectMapper, private val secret: String,
    private val billingSecret: String, private val http: HttpClient): TossGateway {
    @Autowired constructor(json: ObjectMapper,
        @Value("\${app.payment.toss-secret:}") secret: String,
        @Value("\${app.payment.toss-billing-secret:}") billingSecret: String) :
        this(json, secret, billingSecret, HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build())
    private val circuitConfig = CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(20).minimumNumberOfCalls(20).failureRateThreshold(50f)
        .waitDurationInOpenState(java.time.Duration.ofSeconds(30)).permittedNumberOfCallsInHalfOpenState(1)
        .recordException { it is java.io.IOException }
        .ignoreExceptions(InterruptedException::class.java)
        .recordResult { it is HttpResponse<*> && it.statusCode() >= 500 }.build()
    internal val lookupCircuit = CircuitBreaker.of("toss-lookup", circuitConfig)
    internal val transactionsCircuit = CircuitBreaker.of("toss-transactions", circuitConfig)
    override fun confirm(key: String, order: String, amount: Int, idempotency: UUID) = payment(
        call("POST","/v1/payments/confirm",false,idempotency,mapOf("paymentKey" to key,"orderId" to order,"amount" to amount)))
    override fun lookup(order: String, billing: Boolean) = payment(call("GET","/v1/payments/orders/${encode(order)}",billing,circuit=lookupCircuit))
    override fun charge(billingKey: String, customer: String, order: String, amount: Int, name: String, idempotency: UUID) = payment(
        call("POST","/v1/billing/${encode(billingKey)}",true,idempotency,
            mapOf("customerKey" to customer,"orderId" to order,"amount" to amount,"orderName" to name)))
    override fun cancel(paymentKey: String, amount: Int, billing: Boolean, idempotency: UUID) = payment(
        call("POST","/v1/payments/${encode(paymentKey)}/cancel",billing,idempotency,mapOf("cancelReason" to "전액 환불 승인","cancelAmount" to amount)))
    override fun issue(authKey: String, customer: String, idempotency: UUID): PgBilling {
        val response = call("POST","/v1/billing/authorizations/issue",true,idempotency,mapOf("authKey" to authKey,"customerKey" to customer))
        if(response.first != 200 || response.second?.path("customerKey")?.asText() != customer ||
            response.second?.path("billingKey")?.asText().isNullOrBlank()) unavailable()
        return PgBilling(response.second!!.path("billingKey").asText(),customer)
    }
    override fun transactions(from: LocalDate,to: LocalDate,billing: Boolean): List<PgTransaction>? {
        val rows=mutableListOf<PgTransaction>();val cursors=mutableSetOf<String>();var cursor: String?=null
        do {
            val query="startDate=${encode(from.toString()+"T00:00:00")}&endDate=${encode(to.toString()+"T23:59:59")}&limit=100"+
                (cursor?.let { "&startingAfter=${encode(it)}" } ?: "")
            val (status,n)=call("GET","/v1/transactions?$query",billing,timeout=Duration.ofSeconds(60),circuit=transactionsCircuit)
            if(status!=200 || n?.isArray!=true) return null
            val page=try { n.map { row ->
                require(row.path("amount").isIntegralNumber && row.path("amount").canConvertToInt())
                val fields=listOf("transactionKey","orderId","paymentKey","mId","status").map { row.required(it).textValue().also { value -> require(!value.isNullOrBlank()) } }
                PgTransaction(fields[0],fields[1],fields[2],fields[3],row["amount"].intValue(),fields[4])
            } } catch (_: Exception) { return null }
            rows.addAll(page)
            if(page.size<100) return rows
            cursor=page.last().transactionKey
            if(!cursors.add(cursor)) return null
        } while(true)
    }
    private fun call(method: String, path: String, billing: Boolean, key: UUID? = null, body: Any? = null,timeout: Duration=Duration.ofSeconds(6),circuit: CircuitBreaker?=null): Pair<Int,JsonNode?> {
        check(!TransactionSynchronizationManager.isActualTransactionActive()) { "PG calls require no transaction" }
        val credential = if(billing) billingSecret else secret
        if(!(credential.startsWith("test_sk_") || (!billing && credential.startsWith("test_gsk_")))) unavailable()
        return try {
            val request = HttpRequest.newBuilder(URI.create("https://api.tosspayments.com$path"))
                .timeout(timeout).header("Authorization","Basic " + Base64.getEncoder().encodeToString("$credential:".toByteArray()))
                .header("Content-Type","application/json")
            key?.let { request.header("Idempotency-Key",it.toString()) }
            val built = request.method(method,body?.let { HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(it)) }
                ?: HttpRequest.BodyPublishers.noBody()).build()
            val response = if (circuit == null) http.send(built,HttpResponse.BodyHandlers.ofByteArray())
                else circuit.executeSupplier { http.send(built,HttpResponse.BodyHandlers.ofByteArray()) }
            response.statusCode() to json.readTree(response.body())
        } catch (_: InterruptedException) { Thread.currentThread().interrupt(); 0 to null }
          catch (_: Exception) { 0 to null } // Do not log HTTP exceptions: billing key is in PG path.
    }
    private fun payment(response: Pair<Int,JsonNode?>): PgResult {
        val (status,n) = response
        if(status == 404 && n?.path("code")?.asText() == "NOT_FOUND_PAYMENT") return PgResult.Missing
        if(status == 200 && n != null) return try {
            val order=n.required("orderId").textValue(); val key=n.required("paymentKey").textValue()
            val state=n.required("status").textValue(); val mid=n.required("mId").textValue()
            require(!order.isNullOrBlank() && !key.isNullOrBlank() && !mid.isNullOrBlank() && !state.isNullOrBlank())
            require(n.path("totalAmount").isIntegralNumber && n.path("balanceAmount").isIntegralNumber)
            PgResult.Found(PgPayment(order,key,n["totalAmount"].intValue(),state,mid,
                n.path("approvedAt").takeUnless { it.isMissingNode || it.isNull }?.asText()?.let(OffsetDateTime::parse),
                n["balanceAmount"].intValue(),n.path("method").takeUnless { it.isMissingNode || it.isNull }?.asText(),n.required("currency").textValue()))
        } catch (_: Exception) { PgResult.Unknown }
        // Only explicit issuer refusal may advance a renewal to a new charge attempt.
        val code=n?.path("code")?.asText()
        if(status in 400..499 && code in setOf("REJECT_CARD_PAYMENT","REJECT_CARD_COMPANY","INVALID_STOPPED_CARD","INVALID_REJECT_CARD","INVALID_CARD_LOST_OR_STOLEN","EXCEED_MAX_CARD_INSTALLMENT_PLAN","EXCEED_MAX_DAILY_PAYMENT_COUNT","EXCEED_MAX_PAYMENT_AMOUNT","NOT_AVAILABLE_PAYMENT","INVALID_CARD_NUMBER","INVALID_CARD_EXPIRATION","NOT_SUPPORTED_INSTALLMENT_PLAN"))
            return PgResult.Rejected(requireNotNull(code))
        return PgResult.Unknown
    }
    private fun encode(s: String)=URLEncoder.encode(s,StandardCharsets.UTF_8)
    private fun unavailable(): Nothing=throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"PAYMENT_PG_UNAVAILABLE","토스 테스트 결제 설정 또는 응답을 확인해 주세요.")
}
