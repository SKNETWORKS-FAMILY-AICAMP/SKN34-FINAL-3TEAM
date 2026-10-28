package com.sagomungchi.core.learning

import com.sun.net.httpserver.HttpServer
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.learning.client.LearningHttpProperties
import com.sagomungchi.core.learning.client.LearningRecordClient
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.net.InetSocketAddress
import java.time.Duration
import java.util.UUID
import kotlin.test.*

class LearningRecordClientTest {
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
        val client = LearningRecordClient(LearningClient(InternalRestClientFactory(props, RestClient.builder()), LearningHttpProperties(Duration.ofSeconds(1))), jacksonObjectMapper())
        UserContextHolder.set(UserContext("synthetic-parent", "PARENT", setOf(child.toString()), null))
        try {
            payload = "{\"studentId\":\"$child\",\"hasRecords\":false}"
            assertEquals(false, client.exists(child))
            payload = "{\"studentId\":\"$child\",\"hasRecords\":true}"
            assertEquals(true, client.exists(child))
            val invalid = listOf("{}", "invalid-json", payload.replace(child.toString(), UUID.randomUUID().toString()),
                "{\"studentId\":\"$child\",\"hasRecords\":\"false\"}",
                "{\"studentId\":\"$child\",\"hasRecords\":null}")
            for (bad in invalid) {
                payload = bad
                assertNull(client.exists(child))
            }
            code = 503; payload = "{}"
            assertNull(client.exists(child))
            code = 404
            assertNull(client.exists(child))
            assertEquals(9, requests) // no automatic retries
        } finally { UserContextHolder.clear(); server.stop(0) }
    }
}
