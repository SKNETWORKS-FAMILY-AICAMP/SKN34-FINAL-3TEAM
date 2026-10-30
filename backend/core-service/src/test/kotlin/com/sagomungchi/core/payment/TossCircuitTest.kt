package com.sagomungchi.core.payment
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core.payment.client.*
import io.github.resilience4j.circuitbreaker.CircuitBreaker.State
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import java.net.http.*
import java.time.LocalDate
import java.util.UUID
import kotlin.test.*
class TossCircuitTest {
    @Suppress("UNCHECKED_CAST")
    @Test fun `lookup opens on transport and 5xx while 4xx and writes preserve behavior`() {
        val http = mock(HttpClient::class.java)
        val response = mock(HttpResponse::class.java) as HttpResponse<ByteArray>
        var status = 404; var payload = """{"code":"NOT_FOUND_PAYMENT"}"""; var transport = false
        val requests = mutableListOf<HttpRequest>()
        `when`(response.statusCode()).thenAnswer { status }
        `when`(response.body()).thenAnswer { payload.toByteArray() }
        doAnswer { invocation ->
            requests.add(invocation.getArgument(0))
            if (transport) throw HttpTimeoutException("test timeout")
            response
        }.`when`(http).send(any(HttpRequest::class.java), any<HttpResponse.BodyHandler<ByteArray>>())
        val client = TossClient(jacksonObjectMapper(), "test_sk_fixture", "test_sk_fixture", http)
        repeat(20) { assertSame(PgResult.Missing, client.lookup("order", false)) }
        assertEquals(0, client.lookupCircuit.metrics.numberOfFailedCalls)
        status = 503; payload = "{}"
        repeat(10) { assertSame(PgResult.Unknown, client.lookup("order", true)) }
        assertEquals(State.OPEN, client.lookupCircuit.state)
        val before = requests.size
        assertSame(PgResult.Unknown, client.lookup("order", false)); assertEquals(before, requests.size)
        status = 200; payload = "[]"
        assertEquals(emptyList(), client.transactions(LocalDate.now(), LocalDate.now(), false))
        client.transactionsCircuit.transitionToOpenState(); val count = requests.size
        assertNull(client.transactions(LocalDate.now(), LocalDate.now(), true)); assertEquals(count, requests.size)
        val key = UUID.randomUUID()
        client.confirm("payment", "order", 100, key)
        client.charge("billing", "customer", "order", 100, "name", key)
        client.cancel("payment", 100, false, key)
        payload = """{"billingKey":"issued","customerKey":"customer"}"""
        assertEquals("issued", client.issue("auth", "customer", key).billingKey)
        assertEquals(count + 4, requests.size)
        requests.takeLast(4).forEach { assertEquals(key.toString(), it.headers().firstValue("Idempotency-Key").orElseThrow()) }
        client.lookupCircuit.transitionToHalfOpenState(); status = 404; payload = """{"code":"NOT_FOUND_PAYMENT"}"""
        assertSame(PgResult.Missing, client.lookup("order", false)); assertEquals(State.CLOSED, client.lookupCircuit.state)
        transport = true
        repeat(20) { assertSame(PgResult.Unknown, client.lookup("order", false)) }
        assertEquals(State.OPEN, client.lookupCircuit.state)
    }
}
