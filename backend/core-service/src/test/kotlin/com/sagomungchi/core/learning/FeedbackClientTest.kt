package com.sagomungchi.core.learning

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.learning.client.LearningHttpProperties
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class FeedbackClientTest {
    private fun factory(stub: LearningHttpStub) = InternalRestClientFactory(
        AppProperties(AppProperties.Internal("feedback-test-token", Duration.ofSeconds(2), Duration.ofSeconds(30)),
            mapOf("learning" to stub.url)), RestClient.builder())
    private fun feedback(stub: LearningHttpStub, timeout: Duration = Duration.ofSeconds(5)) =
        LearningClient.forFeedback(factory(stub), LearningHttpProperties(timeout), jacksonObjectMapper())
    private fun call(client: LearningClient) = client.exchange("POST", "/answers/test/feedback")
    private val problemHeaders = mapOf("Content-Type" to "application/problem+json;charset=UTF-8")

    @Test fun `learning application failures do not open feedback circuit and default JSON policy is preserved`() = LearningHttpStub().use { stub ->
        val feedback = feedback(stub)
        assertEquals("learning-feedback", feedback.circuit.name)
        for ((status, code) in listOf(503 to "AI_UNAVAILABLE", 500 to "INTERNAL_ERROR")) {
            stub.respond = { LearningHttpStub.Reply(status, """{"status":$status,"code":"$code","retryable":false}""", problemHeaders) }
            repeat(20) { assertEquals(status, call(feedback).status) }
            assertEquals(CircuitBreaker.State.CLOSED, feedback.circuit.state)
            assertEquals(0, feedback.circuit.metrics.numberOfFailedCalls)
        }
        stub.respond = { LearningHttpStub.Reply(200, """{"status":"DONE"}""") }
        assertEquals(200, call(feedback).status)
        val general = LearningClient(factory(stub), LearningHttpProperties(Duration.ofSeconds(5)))
        assertEquals("learning-json", general.circuit.name)
        stub.respond = { LearningHttpStub.Reply(503, """{"code":"AI_UNAVAILABLE"}""", problemHeaders) }
        repeat(20) { assertEquals(503, general.exchange("GET", "/missions").status) }
        assertEquals(CircuitBreaker.State.OPEN, general.circuit.state)
        assertEquals(CircuitBreaker.State.CLOSED, feedback.circuit.state)
    }

    @Test fun `untyped or malformed upstream 5xx still opens feedback circuit without retry`() = LearningHttpStub().use { stub ->
        val replies = listOf(LearningHttpStub.Reply(502, "gateway failure"),
            LearningHttpStub.Reply(503, """{"code":"AI_UNAVAILABLE"}"""),
            LearningHttpStub.Reply(503, "{", problemHeaders),
            LearningHttpStub.Reply(500, """{"code":" "}""", problemHeaders))
        replies.forEach { reply ->
            val client = feedback(stub)
            val before = stub.requests.size
            stub.respond = { reply }
            repeat(20) { assertEquals(reply.status, call(client).status) }
            assertEquals(20, client.circuit.metrics.numberOfFailedCalls)
            assertEquals(CircuitBreaker.State.OPEN, client.circuit.state)
            assertEquals("LEARNING_CIRCUIT_OPEN", assertFailsWith<BusinessException> { call(client) }.code)
            assertEquals(before + 20, stub.requests.size)
        }
    }

    @Test fun `transport failures are counted and open feedback circuit`() {
        val stub = LearningHttpStub()
        val client = feedback(stub)
        stub.close()
        repeat(20) { assertEquals("LEARNING_UNAVAILABLE", assertFailsWith<BusinessException> { call(client) }.code) }
        assertEquals(20, client.circuit.metrics.numberOfFailedCalls)
        assertEquals(CircuitBreaker.State.OPEN, client.circuit.state)
        assertEquals("LEARNING_CIRCUIT_OPEN", assertFailsWith<BusinessException> { call(client) }.code)
    }

    @Test fun `feedback timeout counts one failed call with no automatic retry`() = LearningHttpStub().use { stub ->
        val client = feedback(stub, Duration.ofMillis(200))
        stub.respond = { Thread.sleep(600); LearningHttpStub.Reply() }
        assertEquals("LEARNING_TIMEOUT", assertFailsWith<BusinessException> { call(client) }.code)
        assertEquals(1, client.circuit.metrics.numberOfFailedCalls)
        assertEquals(1, stub.requests.size)
    }
}
