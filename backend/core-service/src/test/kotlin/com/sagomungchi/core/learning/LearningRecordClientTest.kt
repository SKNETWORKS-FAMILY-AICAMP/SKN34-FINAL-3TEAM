package com.sagomungchi.core.learning

import com.sun.net.httpserver.HttpServer
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
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

    /** #824: 근거 원문 응답(EvidenceList)은 client가 계약 타입으로 바꾸고, 틀리면 502 LEARNING_INVALID_RESPONSE. */
    @Test fun `evidence list is typed and outside the contract is 502`() {
        val child = UUID.randomUUID(); var payload = ""
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/internal/records/evidence") { exchange ->
            val bytes = payload.toByteArray()
            exchange.responseHeaders.add("Content-Type", "application/json")
            exchange.sendResponseHeaders(200, bytes.size.toLong()); exchange.responseBody.use { it.write(bytes) }
        }
        server.start()
        val props = AppProperties(AppProperties.Internal("synthetic-internal", Duration.ofSeconds(1), Duration.ofSeconds(1)),
            services = mapOf("learning" to "http://127.0.0.1:${server.address.port}"))
        val client = LearningRecordClient(LearningClient(InternalRestClientFactory(props, RestClient.builder()), LearningHttpProperties(Duration.ofSeconds(1))), jacksonObjectMapper())
        UserContextHolder.set(UserContext("synthetic-parent", "PARENT", setOf(child.toString()), null))
        val answer = UUID.randomUUID(); val attempt = UUID.randomUUID()
        val item = """{"answerId":"$answer","attemptId":"$attempt","missionTitle":"합성 미션","answerVersion":2,"submittedAt":"2026-11-19T01:02:03.456Z","quote":"합성 원문","available":true}"""
        val removed = """{"answerId":"$answer","attemptId":null,"missionTitle":null,"answerVersion":null,"submittedAt":null,"quote":null,"available":false}"""
        try {
            payload = """{"items":[$item,$removed]}"""
            val records = client.evidence(listOf(answer))
            assertEquals(com.sagomungchi.core.learning.client.EvidenceRecord(answer, attempt, "합성 미션", 2, "2026-11-19T01:02:03.456Z", "합성 원문", true), records[0])
            assertEquals(java.time.Instant.parse("2026-11-19T01:02:03.456Z"), records[0].submittedInstant)
            assertEquals(com.sagomungchi.core.learning.client.EvidenceRecord(answer, null, null, null, null, null, false), records[1])
            fun with(field: String, value: String) = item.replace(Regex("\"$field\":(\"[^\"]*\"|[^,}]*)"), "\"$field\":$value")
            val broken = listOf("{}", """{"items":{}}""", """{"items":["x"]}""", """{"items":[${with("answerId", "\"x\"")}]}""",
                """{"items":[${with("answerId", "null")}]}""", """{"items":[${with("attemptId", "\"x\"")}]}""",
                """{"items":[${item.replace(",\"attemptId\":\"$attempt\"", "")}]}""",
                """{"items":[${with("answerVersion", "\"2\"")}]}""", """{"items":[${with("answerVersion", "1.5")}]}""",
                """{"items":[${with("submittedAt", "\"어제\"")}]}""", """{"items":[${with("quote", "1")}]}""",
                """{"items":[${with("missionTitle", "{}")}]}""", """{"items":[${with("available", "\"true\"")}]}""",
                """{"items":[${with("available", "null")}]}""", "invalid-json")
            for (bad in broken) {
                payload = bad
                val error = assertFailsWith<com.sagomungchi.core._common.exception.BusinessException>(bad) { client.evidence(listOf(answer)) }
                assertEquals("LEARNING_INVALID_RESPONSE", error.code, bad); assertEquals(502, error.status.value())
            }
        } finally { UserContextHolder.clear(); server.stop(0) }
    }
}
