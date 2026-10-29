package com.sagomungchi.core.conversation

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.conversation.client.AiClient
import com.sagomungchi.core.conversation.client.AnalysisCall
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
            exchange.responseBody.write(": ping\nevent: status\ndata: {\ndata: \"state\":\"RUNNING\"}\n\n".toByteArray())
            exchange.event("done", "{}")
        }
        val ai = client(stub)
        try {
            val events = mutableListOf<String>()
            ai.stream(mapOf("question" to "합성 질문"), AnalysisCall()) { name, _ -> events.add(name) }
            assertEquals(listOf("status", "done"), events); assertEquals(1, stub.requests.size)
        } finally { ai.close() }
    }
    @Test fun `heartbeat and HTTP headers do not satisfy first AI event deadline`() = AnalysisHttpStub().use { stub ->
        val release = CountDownLatch(1)
        stub.respond = { exchange, _ -> exchange.responseBody.write(": ping\n\n".toByteArray()); exchange.responseBody.flush(); release.await(3, TimeUnit.SECONDS) }
        val ai = client(stub, 120, 1000)
        try { assertEquals("ANALYSIS_FIRST_RESPONSE_TIMEOUT", assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _, _ -> } }.code) }
        finally { release.countDown(); ai.close() }
    }
    @Test fun `total deadline applies after first event and closes pending stream`() = AnalysisHttpStub().use { stub ->
        val release = CountDownLatch(1)
        stub.respond = { exchange, _ -> exchange.event("status", "{}" ); release.await(3, TimeUnit.SECONDS) }
        val ai = client(stub, 500, 150)
        try { assertEquals("ANALYSIS_TIMEOUT", assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _, _ -> } }.code) }
        finally { release.countDown(); ai.close() }
    }
    @Test fun `explicit cancellation interrupts upstream before further events`() = AnalysisHttpStub().use { stub ->
        val entered = CountDownLatch(1); val release = CountDownLatch(1); val call = AnalysisCall()
        stub.respond = { exchange, _ -> exchange.event("status", "{}"); entered.countDown(); release.await(3, TimeUnit.SECONDS) }
        val ai = client(stub); val executor = Executors.newVirtualThreadPerTaskExecutor()
        try {
            val task = executor.submit<String> {
                assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), call) { _, _ -> } }.code
            }
            assertTrue(entered.await(2, TimeUnit.SECONDS)); call.cancel("STREAM_INTERRUPTED")
            assertEquals("STREAM_INTERRUPTED", task.get(2, TimeUnit.SECONDS))
        } finally { release.countDown(); executor.close(); ai.close() }
    }
    @Test fun `EOF malformed JSON unknown content and oversized frames fail explicitly`() = AnalysisHttpStub().use { stub ->
        val ai = client(stub)
        try {
            for (payload in listOf("event: delta\ndata: {}\n\n", "event: result\ndata: {\n\n", "data: " + "x".repeat(262145))) {
                stub.respond = { exchange, _ -> exchange.responseBody.write(payload.toByteArray()); exchange.responseBody.flush() }
                assertEquals("AI_INVALID_RESPONSE", assertFailsWith<BusinessException> { ai.stream(emptyMap<String, String>(), AnalysisCall()) { _, _ -> } }.code)
            }
        } finally { ai.close() }
    }
}
