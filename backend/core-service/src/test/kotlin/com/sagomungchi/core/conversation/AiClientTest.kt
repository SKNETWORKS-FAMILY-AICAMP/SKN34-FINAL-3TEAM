package com.sagomungchi.core.conversation

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.conversation.client.AiClient
import com.sagomungchi.core.conversation.client.AnalysisCall
import com.sagomungchi.core.conversation.client.AnalysisEvent
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.Executors
import kotlin.test.*

class AiClientTest {
    private fun client(stub: AnalysisHttpStub, first: Long = 1000, total: Long = 2000) = AiClient(
        InternalRestClientFactory(AppProperties(AppProperties.Internal("analysis-test-token", Duration.ofSeconds(1), Duration.ofSeconds(2)),
            mapOf("ai" to stub.url)), RestClient.builder()), jacksonObjectMapper(), Duration.ofMillis(first), Duration.ofMillis(total))

    @Test fun `SSE parser ignores comments and accepts multiline JSON without retry`() = AnalysisHttpStub().use { stub ->
        stub.respond = { exchange, _ ->
            exchange.responseBody.write(": ping\nevent: status\ndata: {\ndata: \"state\":\"RUNNING\",\"message\":\"조회 중\"}\n\n".toByteArray())
            exchange.event("done", "{}")
        }
        val ai = client(stub)
        try {
            val events = mutableListOf<AnalysisEvent>()
            ai.stream(mapOf("question" to "합성 질문"), AnalysisCall()) { event -> events.add(event) }
            assertEquals(listOf(AnalysisEvent.Status("조회 중"), AnalysisEvent.Done), events); assertEquals(1, stub.requests.size)
        } finally { ai.close() }
    }
    @Test fun `typed events carry only checked fields and result bodies pass through`() = AnalysisHttpStub().use { stub ->
        stub.respond = { e, _ ->
            e.event("status", STATUS); e.event("delta", """{"text":"부분"}""")
            e.event("result", """{"answer":"합성"}"""); e.event("done", "{}")
        }
        val ai = client(stub)
        try {
            val events = mutableListOf<AnalysisEvent>()
            ai.stream(emptyMap<String, String>(), AnalysisCall()) { events.add(it) }
            assertEquals(listOf(AnalysisEvent.Status("조회 중"), AnalysisEvent.Delta("부분")), events.take(2))
            assertEquals("합성", (events[2] as AnalysisEvent.Result).body["answer"].asText())
            assertEquals(AnalysisEvent.Done, events[3])
            stub.respond = { e, _ -> e.event("error", """{"code":"ANALYSIS_FAILED","detail":"공급자 원문"}""") }
            events.clear()
            ai.stream(emptyMap<String, String>(), AnalysisCall()) { events.add(it) }
            assertEquals(listOf<AnalysisEvent>(AnalysisEvent.Error("ANALYSIS_FAILED")), events)
        } finally { ai.close() }
    }
    @Test fun `malformed event shapes fail as AI_INVALID_RESPONSE before reaching the consumer`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            for ((name, data) in listOf("status" to """{"state":"DONE","message":"조회 중"}""", "status" to """{"state":"RUNNING"}""",
                "delta" to """{"text":1}""", "error" to """{"code":"lower"}""", "error" to "{}", "unknown" to "{}")) {
                stub.respond = { e, _ -> e.event(name, data) }
                var consumed = false
                assertEquals("AI_INVALID_RESPONSE", assertFailsWith<BusinessException> {
                    ai.stream(emptyMap<String, String>(), AnalysisCall()) { consumed = true }
                }.code, "$name $data")
                assertFalse(consumed, "$name $data")
            }
        } finally { ai.close() }
    }
    @Test fun `heartbeat and HTTP headers do not satisfy first AI event deadline`() = AnalysisHttpStub().use { stub ->
        val release = CountDownLatch(1)
        stub.respond = { exchange, _ -> exchange.responseBody.write(": ping\n\n".toByteArray()); exchange.responseBody.flush(); release.await(3, TimeUnit.SECONDS) }
        val ai = client(stub, 120, 1000)
        try { assertEquals("ANALYSIS_FIRST_RESPONSE_TIMEOUT", assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> } }.code) }
        finally { assertEquals(1, ai.circuit.metrics.numberOfFailedCalls); release.countDown(); ai.close() }
    }
    @Test fun `total deadline applies after first event and closes pending stream`() = AnalysisHttpStub().use { stub ->
        val release = CountDownLatch(1)
        stub.respond = { exchange, _ -> exchange.event("status", STATUS); release.await(3, TimeUnit.SECONDS) }
        val ai = client(stub, 500, 150)
        try { assertEquals("ANALYSIS_TIMEOUT", assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> } }.code) }
        finally { assertEquals(1, ai.circuit.metrics.numberOfFailedCalls); release.countDown(); ai.close() }
    }
    @Test fun `explicit cancellation interrupts upstream before further events`() = AnalysisHttpStub().use { stub ->
        val entered = CountDownLatch(1); val release = CountDownLatch(1); val call = AnalysisCall()
        stub.respond = { exchange, _ -> exchange.event("status", STATUS); entered.countDown(); release.await(3, TimeUnit.SECONDS) }
        val ai = client(stub); val executor = Executors.newVirtualThreadPerTaskExecutor()
        try {
            val task = executor.submit<String> {
                assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), call) { _ -> } }.code
            }
            assertTrue(entered.await(2, TimeUnit.SECONDS)); call.cancel("STREAM_INTERRUPTED")
            assertEquals("STREAM_INTERRUPTED", task.get(2, TimeUnit.SECONDS))
            assertEquals(0, ai.circuit.metrics.numberOfBufferedCalls)
        } finally { release.countDown(); executor.close(); ai.close() }
    }
    @Test fun `EOF malformed JSON unknown content and oversized frames fail explicitly`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            for (payload in listOf("event: delta\ndata: {}\n\n", "event: result\ndata: {\n\n", "data: " + "x".repeat(262145))) {
                stub.respond = { exchange, _ -> exchange.responseBody.write(payload.toByteArray()); exchange.responseBody.flush() }
                assertEquals("AI_INVALID_RESPONSE", assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> } }.code)
            }
        } finally { ai.close() }
    }

    @Test fun `failed streams open circuit without another HTTP request and half open recovers`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            repeat(20) { assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> } } }
            assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN, ai.circuit.state)
            assertEquals("AI_UNAVAILABLE", assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> } }.code)
            assertEquals(20, stub.requests.size)
            ai.circuit.transitionToHalfOpenState()
            stub.respond = { e, _ -> e.event("done", "{}") }
            ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> }
            assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED, ai.circuit.state)
            assertNull(stub.requests.last().header("Upgrade"))
        } finally { ai.close() }
    }
    @Test fun `HTTP 4xx are not circuit failures but 5xx are`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            stub.status = 429
            repeat(20) { assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> } } }
            assertEquals(0, ai.circuit.metrics.numberOfFailedCalls)
            stub.status = 503
            assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> } }
            assertEquals(1, ai.circuit.metrics.numberOfFailedCalls)
        } finally { ai.close() }
    }
    @Test fun `error terminal fails circuit and normal terminal succeeds`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            stub.respond = { e, _ -> e.event("error", """{"code":"ANALYSIS_FAILED"}""") }
            ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> }
            assertEquals(1, ai.circuit.metrics.numberOfFailedCalls)
            stub.respond = { e, _ -> e.event("result", "{}"); e.event("done", "{}") }
            ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> }
            assertEquals(1, ai.circuit.metrics.numberOfSuccessfulCalls)
        } finally { ai.close() }
    }
    @Test fun `local consumer failure releases half open permit`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            ai.circuit.transitionToOpenState(); ai.circuit.transitionToHalfOpenState()
            stub.respond = { e, _ -> e.event("status", STATUS) }
            assertFailsWith<BusinessException> {
                ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ ->
                    throw BusinessException(org.springframework.http.HttpStatus.FORBIDDEN, "FORBIDDEN", "denied")
                }
            }
            assertEquals(0, ai.circuit.metrics.numberOfBufferedCalls)
            stub.respond = { e, _ -> e.event("clarification", "{}") }
            ai.stream(emptyMap<String, String>(), AnalysisCall()) { _ -> }
            assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED, ai.circuit.state)
        } finally { ai.close() }
    }

    @Test fun `report template failures open only its own circuit and half open recovers`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            stub.status = 503
            repeat(10) { assertEquals("AI_UNAVAILABLE", assertFailsWith<BusinessException> { ai.reportTemplate(emptyMap<String, String>()) }.code) }
            assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN, ai.templateCircuit.state)
            assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED, ai.circuit.state)
            assertEquals("AI_UNAVAILABLE", assertFailsWith<BusinessException> { ai.reportTemplate(emptyMap<String, String>()) }.code)
            assertEquals(10, stub.requests.size)
            ai.templateCircuit.transitionToHalfOpenState()
            stub.status = 200
            assertEquals("확인", ai.reportTemplate(emptyMap<String, String>()).get("clarification").asText())
            assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED, ai.templateCircuit.state)
        } finally { ai.close() }
    }
    @Test fun `report template HTTP 4xx is not a circuit failure`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            stub.status = 400
            repeat(10) { assertEquals("AI_UNAVAILABLE", assertFailsWith<BusinessException> { ai.reportTemplate(emptyMap<String, String>()) }.code) }
            assertEquals(0, ai.templateCircuit.metrics.numberOfFailedCalls)
            assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED, ai.templateCircuit.state)
        } finally { ai.close() }
    }

    private companion object { const val STATUS = """{"state":"RUNNING","message":"조회 중"}""" }
}
