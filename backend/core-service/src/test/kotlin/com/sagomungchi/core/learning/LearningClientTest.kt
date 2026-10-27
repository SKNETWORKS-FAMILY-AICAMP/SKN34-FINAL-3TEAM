package com.sagomungchi.core.learning

import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.learning.client.LearningHttpProperties
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import kotlin.test.*

class LearningClientTest {
    private fun client(stub: LearningHttpStub, timeout: Duration = Duration.ofSeconds(2)) = LearningClient(
        InternalRestClientFactory(AppProperties(AppProperties.Internal("server-secret", Duration.ofSeconds(2), Duration.ofSeconds(30)),
            mapOf("learning" to stub.url)), RestClient.builder()), LearningHttpProperties(timeout))

    @Test fun `wire preserves encoded queries response bytes status and allowed headers only`() = LearningHttpStub().use { stub ->
        stub.respond = { LearningHttpStub.Reply(409, "{ \"status\":409,\"code\":\"ATTEMPT_DRAFT_CONFLICT\",\"latest\":{\"memo\":\"생각\"}}",
            mapOf("Content-Type" to "application/problem+json", "ETag" to "\"8\"", "Retry-After" to "2", "Set-Cookie" to "unsafe=1")) }
        UserContextHolder.set(UserContext("verified-user", "STUDENT", setOf("verified-child"), "00-123-456-01"))
        try {
            val result = client(stub).exchange("PUT", "/attempts/a/draft", "q=a%2Bb%20c&tag=1&tag=2", "{\"memo\":\"생각\"}".toByteArray(), "\"7\"")
            assertEquals(409, result.status)
            assertEquals(stub.respond(stub.requests.single()).body, result.body.toString(Charsets.UTF_8))
            assertEquals("/internal/attempts/a/draft?q=a%2Bb%20c&tag=1&tag=2", stub.requests.single().target)
            assertEquals("\"7\"", stub.requests.single().header("If-Match"))
            assertEquals("verified-child", stub.requests.single().header("X-Student-Scope"))
            assertEquals("server-secret", stub.requests.single().header("X-Internal-Token"))
            assertFalse(result.headers.keys.any { it.equals("Set-Cookie", true) })
        } finally { UserContextHolder.clear() }
    }

    @Test fun `timeout is 504 and does not automatically retry`() = LearningHttpStub().use { stub ->
        stub.respond = { Thread.sleep(600); LearningHttpStub.Reply() }
        val ex = assertFailsWith<BusinessException> { client(stub, Duration.ofMillis(100)).exchange("GET", "/missions") }
        assertEquals("LEARNING_TIMEOUT", ex.code)
        assertEquals(504, ex.status.value())
        assertEquals(1, stub.requests.size)
    }

    @Test fun `connection loss is explicit 503 with one failed attempt`() {
        val stub = LearningHttpStub()
        val client = client(stub)
        stub.close()
        val ex = assertFailsWith<BusinessException> { client.exchange("GET", "/missions") }
        assertEquals("LEARNING_UNAVAILABLE", ex.code); assertEquals(503, ex.status.value())
        assertEquals(1, client.circuit.metrics.numberOfFailedCalls)
        assertEquals(Duration.ofSeconds(30), LearningHttpProperties().readTimeout)
    }

    @Test fun `twenty calls with fifty percent failures open circuit and half open success recovers`() = LearningHttpStub().use { stub ->
        val client = client(stub)
        stub.respond = { LearningHttpStub.Reply(422) }
        repeat(10) { assertEquals(422, client.exchange("GET", "/missions").status) }
        stub.respond = { LearningHttpStub.Reply(503, "{\"code\":\"OVERLOADED\"}") }
        repeat(10) { assertEquals(503, client.exchange("GET", "/missions").status) }
        assertEquals(CircuitBreaker.State.OPEN, client.circuit.state)
        val ex = assertFailsWith<BusinessException> { client.exchange("GET", "/missions") }
        assertEquals("LEARNING_CIRCUIT_OPEN", ex.code)
        assertEquals(20, stub.requests.size)
        assertEquals(30_000L, client.circuit.circuitBreakerConfig.waitIntervalFunctionInOpenState.apply(1))
        client.circuit.transitionToHalfOpenState()
        stub.respond = { LearningHttpStub.Reply() }
        client.exchange("GET", "/missions")
        assertEquals(CircuitBreaker.State.CLOSED, client.circuit.state)
    }

    @Test fun `client errors do not trip circuit and half open failure opens again`() = LearningHttpStub().use { stub ->
        val client = client(stub)
        stub.respond = { LearningHttpStub.Reply(403) }
        repeat(20) { client.exchange("GET", "/missions") }
        assertEquals(CircuitBreaker.State.CLOSED, client.circuit.state)
        client.circuit.transitionToOpenState(); client.circuit.transitionToHalfOpenState()
        stub.respond = { LearningHttpStub.Reply(502) }
        client.exchange("GET", "/missions")
        assertEquals(CircuitBreaker.State.OPEN, client.circuit.state)
    }
}
