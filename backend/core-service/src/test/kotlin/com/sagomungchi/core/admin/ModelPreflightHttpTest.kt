package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.domain.RegistrationArtifact
import com.sagomungchi.core.admin.service.*
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.net.InetSocketAddress
import kotlin.test.*

@AutoConfigureMockMvc
class ModelPreflightHttpTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var json: ObjectMapper
    private fun body() = ModelPreflightRequest("m2-klue-narrative", "3.0", "s3://models/models/test/3.0/",
        PREFLIGHT_FILES.map { RegistrationArtifact(it, 1, "a".repeat(64)) })
    private fun success() = ModelPreflightResult("PASS", "FILES_AND_METADATA_VERIFIED", PREFLIGHT_FILES.map { PreflightFileResult(it, "PASS", "OK") })
    @BeforeEach fun setup() { response = json.writeValueAsString(success()); upstreamStatus = 200; received = ""; internalToken = "" }
    private fun call(body: Any, permission: String? = "SERVICE_OPS") = mvc.post("/api/v1/admin/models/preflight") {
        val actor = account(jdbc, permission = permission)
        header("Authorization", "Bearer ${tokens.access(session(jdbc, actor))}")
        contentType = MediaType.APPLICATION_JSON; content = json.writeValueAsString(body)
    }
    @Test fun `read only preflight relays internal token and records success without registration`() {
        call(body()).andExpect { status { isOk() }; jsonPath("$.status") { value("PASS") } }
        assertEquals("repository-test-token", internalToken)
        assertEquals(6, json.readTree(received)["files"].size())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE action='MODEL_PREFLIGHT' AND result='SUCCESS'", Int::class.java))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM model_version", Int::class.java))
    }
    @Test fun `file failure is recorded as FAILURE and is not an activation`() {
        response = json.writeValueAsString(ModelPreflightResult("FAIL", "FILE_CHECK_FAILED", listOf(PreflightFileResult("model.safetensors", "FAIL", "HASH_MISMATCH"))))
        call(body()).andExpect { status { isOk() }; jsonPath("$.status") { value("FAIL") } }
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE action='MODEL_PREFLIGHT' AND result='FAILURE'", Int::class.java))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE event_type='model.version.activated'", Int::class.java))
    }
    @Test fun `upstream error and invalid success are safe and audited`() {
        upstreamStatus = 500; response = "provider private detail"
        call(body()).andExpect { status { isBadGateway() }; jsonPath("$.code") { value("MODEL_PREFLIGHT_INVALID_RESPONSE") } }
        upstreamStatus = 200; response = """{"status":"PASS","code":"FILES_AND_METADATA_VERIFIED","files":[]}"""
        call(body()).andExpect { status { isBadGateway() } }
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE action='MODEL_PREFLIGHT' AND result='FAILURE'", Int::class.java))
    }
    @Test fun `SERVICE_OPS permission and strict file contract are required`() {
        call(body(), null).andExpect { status { isForbidden() } }
        call(body().copy(files=body().files.take(5))).andExpect { status { isBadRequest() } }
        val unknown = json.convertValue(body(), Map::class.java) + mapOf("approved" to true)
        call(unknown).andExpect { status { isBadRequest() } }
        assertEquals("", received)
    }
    companion object {
        @Volatile var response = "{}"
        @Volatile var upstreamStatus = 200
        @Volatile var received = ""
        @Volatile var internalToken = ""
        private val upstream = HttpServer.create(InetSocketAddress("0.0.0.0", 0), 0).apply {
            createContext("/internal/models/preflight") { exchange ->
                received = exchange.requestBody.bufferedReader().readText()
                internalToken = exchange.requestHeaders.getFirst("X-Internal-Token") ?: ""
                val data = response.toByteArray(); exchange.responseHeaders.add("Content-Type", "application/json")
                exchange.sendResponseHeaders(upstreamStatus, data.size.toLong()); exchange.responseBody.use { it.write(data) }
            }; start()
        }
        @JvmStatic @DynamicPropertySource fun scoring(registry: DynamicPropertyRegistry) {
            registry.add("app.services.scoring") { "http://127.0.0.1:${upstream.address.port}" }
        }
    }
}
