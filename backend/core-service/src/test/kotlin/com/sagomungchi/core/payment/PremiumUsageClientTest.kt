package com.sagomungchi.core.payment

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.payment.client.PremiumUsageClient
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.net.InetSocketAddress
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

/** 실제 learning 사용 증빙 client: 확인 실패는 모두 503 REFUND_USAGE_UNAVAILABLE (자체 unavailable, #168) */
class PremiumUsageClientTest {
    private val student = UUID.randomUUID()
    private val since = OffsetDateTime.parse("2026-10-28T01:00:00Z")

    private fun call(status: Int, body: String): Result<Boolean> {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            createContext("/internal/payment-usage/students/") { exchange ->
                val bytes = body.toByteArray()
                exchange.responseHeaders.set("Content-Type", "application/json")
                exchange.sendResponseHeaders(status, bytes.size.toLong()); exchange.responseBody.write(bytes); exchange.close()
            }
            start()
        }
        return try {
            val factory = InternalRestClientFactory(AppProperties(AppProperties.Internal("usage-test-token", Duration.ofSeconds(1), Duration.ofSeconds(2)),
                mapOf("learning" to "http://127.0.0.1:${server.address.port}")), RestClient.builder())
            runCatching { PremiumUsageClient(factory, jacksonObjectMapper()).used(student, since) }
        } finally { server.stop(0) }
    }

    @Test fun `matching proof returns used and every failed check is 503 REFUND_USAGE_UNAVAILABLE`() {
        assertEquals(true, call(200, """{"studentId":"$student","since":"2026-10-28T01:00:00Z","used":true}""").getOrThrow())
        listOf(500 to "{}", 200 to """{"studentId":"${UUID.randomUUID()}","since":"2026-10-28T01:00:00Z","used":true}""",
            200 to """{"studentId":"$student","since":"2026-10-28T01:00:00Z","used":"yes"}""", 200 to "not json").forEach { (status, body) ->
            val error = assertIs<BusinessException>(call(status, body).exceptionOrNull())
            assertEquals(503 to "REFUND_USAGE_UNAVAILABLE", error.status.value() to error.code)
        }
    }
}
