package com.sagomungchi.core.payment.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID

@Component
class PremiumUsageClient(factory: InternalRestClientFactory, private val json: ObjectMapper) {
    private val client=factory.create("learning",Duration.ofSeconds(5))
    fun used(student: UUID, since: OffsetDateTime): Boolean {
        check(!TransactionSynchronizationManager.isActualTransactionActive())
        val previous=UserContextHolder.currentOrNull()
        UserContextHolder.set(UserContext(null,"SYSTEM",setOf(student.toString()),previous?.traceparent))
        return try {
            client.get().uri { b -> b.path("/internal/payment-usage/students/{student}").queryParam("since",since.toString()).build(student) }
                .exchange { _, response ->
                    if(response.statusCode.value()!=200) unavailable("REFUND_USAGE_UNAVAILABLE")
                    val n=json.readTree(response.body)
                    if(n.path("studentId").asText()!=student.toString() || n.path("since").asText().let { OffsetDateTime.parse(it).toInstant() } != since.toInstant() || !n.path("used").isBoolean)
                        unavailable("REFUND_USAGE_UNAVAILABLE")
                    n["used"].booleanValue()
                }!!
        } catch (_: Exception) { unavailable("REFUND_USAGE_UNAVAILABLE") }
        finally { if(previous==null) UserContextHolder.clear() else UserContextHolder.set(previous) }
    }
}
