package com.sagomungchi.core.guardianship

import com.sun.net.httpserver.HttpServer
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.client.ChildRecordsClient
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.net.InetSocketAddress
import java.time.Duration
import java.util.UUID
import kotlin.test.*

class ChildRecordsClientTest {
    @Test fun `real HTTP contract forwards verified scope and distinguishes absence from failure`() {
        val child = UUID.randomUUID(); var code = 200; var payload = ""; var requests = 0
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/internal/records/students/$child/exists") { exchange ->
            requests++
            assertEquals("synthetic-internal", exchange.requestHeaders.getFirst("X-Internal-Token"))
            assertEquals(child.toString(), exchange.requestHeaders.getFirst("X-Student-Scope"))
            assertNull(exchange.requestURI.rawQuery)
            val bytes = payload.toByteArray()
            exchange.responseHeaders.add("Content-Type", "application/json")
            exchange.sendResponseHeaders(code, bytes.size.toLong()); exchange.responseBody.use { it.write(bytes) }
        }
        server.start()
        val props = AppProperties(AppProperties.Internal("synthetic-internal", Duration.ofSeconds(1), Duration.ofSeconds(1)),
            services = mapOf("learning" to "http://127.0.0.1:${server.address.port}"))
        val client = ChildRecordsClient(InternalRestClientFactory(props, RestClient.builder()))
        UserContextHolder.set(UserContext("synthetic-parent", "PARENT", setOf(child.toString()), null))
        try {
            payload = "{\"studentId\":\"$child\",\"hasRecords\":false}"
            assertEquals(false, client.records(child).hasRecords)
            assertEquals("AVAILABLE", client.records(child).recordState)
            payload = "{\"studentId\":\"$child\",\"hasRecords\":true}"
            assertEquals(true, client.records(child).hasRecords)
            val invalid = listOf("{}", "invalid-json", payload.replace(child.toString(), UUID.randomUUID().toString()),
                "{\"studentId\":\"$child\",\"hasRecords\":\"false\"}",
                "{\"studentId\":\"$child\",\"hasRecords\":null}")
            for (bad in invalid) {
                payload = bad
                assertEquals("UNAVAILABLE", client.records(child).recordState)
            }
            code = 503; payload = "{}"
            assertNull(client.records(child).hasRecords)
            code = 404
            assertEquals("UNAVAILABLE", client.records(child).recordState)
            assertEquals(10, requests) // no automatic retries
        } finally { UserContextHolder.clear(); server.stop(0) }
    }
}
