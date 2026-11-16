package com.sagomungchi.core.payment

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
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

/**
 * 실제 learning 사용 증빙 client: 확인 실패는 모두 503 REFUND_USAGE_UNAVAILABLE (자체 unavailable, #168).
 * 전송은 공용 LearningClient의 `learning-json` 서킷을 함께 쓰고 응답 시간 5초는 그대로다(#654)
 */
class PremiumUsageClientTest {
    private val student = UUID.randomUUID()
    private val since = OffsetDateTime.parse("2026-10-28T10:00:00+09:00")
    private val proof = """{"studentId":"$student","since":"2026-10-28T01:00:00Z","used":true}"""

    private class Learning(private val student: UUID, private val since: OffsetDateTime, val status: Int, val body: String) : AutoCloseable {
        var delay: Duration = Duration.ZERO
        val targets = mutableListOf<String>()
        private val server: HttpServer = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            createContext("/internal/payment-usage/students/") { exchange ->
                synchronized(targets) { targets += exchange.requestURI.rawPath + "?" + exchange.requestURI.rawQuery }
                Thread.sleep(delay.toMillis())
                val bytes = body.toByteArray()
                exchange.responseHeaders.set("Content-Type", "application/json")
                exchange.sendResponseHeaders(status, bytes.size.toLong()); exchange.responseBody.write(bytes); exchange.close()
            }
            executor = java.util.concurrent.Executors.newCachedThreadPool()
            start()
        }
        val learning = LearningClient(InternalRestClientFactory(AppProperties(AppProperties.Internal("usage-test-token", Duration.ofSeconds(1), Duration.ofSeconds(2)),
            mapOf("learning" to "http://127.0.0.1:${server.address.port}")), RestClient.builder()), LearningHttpProperties())
        val client = PremiumUsageClient(learning, jacksonObjectMapper())
        fun call() = runCatching { client.used(student, since) }
        override fun close() = server.stop(0)
    }

    private fun learning(status: Int = 200, body: String = proof) = Learning(student, since, status, body)
    private fun assertUnavailable(result: Result<Boolean>) {
        val error = assertIs<BusinessException>(result.exceptionOrNull())
        assertEquals(503 to "REFUND_USAGE_UNAVAILABLE", error.status.value() to error.code)
    }

    @Test fun `matching proof returns used and every failed check is 503 REFUND_USAGE_UNAVAILABLE`() {
        learning().use { stub ->
            assertEquals(true, stub.call().getOrThrow())
            assertEquals("/internal/payment-usage/students/$student?since=2026-10-28T10%3A00%2B09%3A00", stub.targets.single())
        }
        listOf(500 to "{}", 200 to """{"studentId":"${UUID.randomUUID()}","since":"2026-10-28T01:00:00Z","used":true}""",
            200 to """{"studentId":"$student","since":"2026-10-28T01:00:00Z","used":"yes"}""", 200 to "not json").forEach { (status, body) ->
            learning(status, body).use { assertUnavailable(it.call()) }
        }
    }

    @Test fun `open shared learning circuit is the same unavailable result without calling learning`() = learning().use { stub ->
        stub.learning.circuit.transitionToOpenState()
        assertUnavailable(stub.call())
        assertTrue(stub.targets.isEmpty())
    }

    @Test fun `usage proof failures count on the shared learning-json circuit`() = learning(503, "{}").use { stub ->
        assertEquals("learning-json", stub.learning.circuit.name)
        repeat(20) { assertUnavailable(stub.call()) }
        assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN, stub.learning.circuit.state)
        assertEquals(20, stub.targets.size)
    }

    @Test fun `usage proof keeps its five second response limit instead of the general thirty seconds`() = learning().use { stub ->
        stub.delay = Duration.ofSeconds(6)
        val started = System.nanoTime()
        assertUnavailable(stub.call())
        val elapsed = Duration.ofNanos(System.nanoTime() - started)
        assertTrue(elapsed >= Duration.ofSeconds(5) && elapsed < Duration.ofSeconds(6), "elapsed=$elapsed")
        assertEquals(1, stub.learning.circuit.metrics.numberOfFailedCalls)
    }
}
