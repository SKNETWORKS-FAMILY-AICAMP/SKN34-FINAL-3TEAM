package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.security.InternalCallerPolicy
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.domain.*
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
import java.util.UUID
import kotlin.test.*

/** 재학습 작업(ops) 자동 등록 `POST /internal/model-versions` (api-spec 5.2.3, #728) */
@AutoConfigureMockMvc
class PipelineRegistrationHttpTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var properties: AppProperties

    private val pipeline = UUID.fromString("00000000-0000-4000-8000-0000000f0725")
    private val files = preflightFiles("tox-kcelectra").map { mapOf("file" to it, "bytes" to 1, "sha256" to "a".repeat(64)) }
    private val recommendation = mapOf("tag" to "RECOMMENDED", "comparedTo" to "tox-kcelectra:20261101-0300",
        "reasons" to listOf("같은 평가 세트에서 놓친 글이 줄었다"), "metrics" to mapOf("recall" to 0.96, "precision" to 0.99))
    private fun body(name: String = "tox-kcelectra", version: String = "20261121-0300", kind: String = "MODEL",
                     recommendation: Any? = this.recommendation, registration: Any? = mapOf("source" to "PIPELINE",
                         "datasetSha256" to "b".repeat(64), "artifactFiles" to files)): Map<String, Any?> {
        val evaluation = json.convertValue(evidence(listOf("answer-filter")), Map::class.java).toMutableMap()
        evaluation.remove("recommendation"); recommendation?.let { evaluation["recommendation"] = it }
        return mapOf("kind" to kind, "name" to name, "version" to version,
            "artifactUri" to "s3://test-models/models/$name/$version/", "evaluation" to evaluation) +
            (if (registration == null) emptyMap() else mapOf("registration" to registration))
    }
    private fun call(body: Any, token: String? = properties.internal.token) = mvc.post("/internal/model-versions") {
        token?.let { header("X-Internal-Token", it) }
        contentType = MediaType.APPLICATION_JSON; content = json.writeValueAsString(body)
    }
    private fun count(sql: String, vararg args: Any) = jdbc.queryForObject(sql, Int::class.java, *args)
    private fun audit(action: String) = jdbc.queryForList(
        "SELECT actor_user_id, result, detail::text AS detail FROM audit_log WHERE action=?", action)

    @BeforeEach fun setup() {
        response = json.writeValueAsString(ModelPreflightResult("PASS", "FILES_AND_METADATA_VERIFIED",
            preflightFiles("tox-kcelectra").map { PreflightFileResult(it, "PASS", "OK") }))
        upstreamStatus = 200; received = ""
    }

    @Test fun `PASS registers REGISTERED with recommendation as the pipeline account and does not activate`() {
        assertEquals(pipeline, properties.modelRegistry.pipelineActorId)
        call(body()).andExpect {
            status { isCreated() }
            jsonPath("$.status") { value("REGISTERED") }
            jsonPath("$.evalResult.evidence.recommendation.tag") { value("RECOMMENDED") }
            jsonPath("$.evalResult.evidence.recommendation.metrics.recall") { value(0.96) }
        }
        assertEquals(5, json.readTree(received)["files"].size())
        val preflight = audit("MODEL_PREFLIGHT").single()
        assertEquals(pipeline, preflight["actor_user_id"]); assertEquals("SUCCESS", preflight["result"])
        val register = audit("MODEL_REGISTER").single()
        assertEquals(pipeline, register["actor_user_id"])
        val detail = json.readTree(register["detail"] as String)
        assertEquals("PIPELINE", detail["source"].asText())
        assertEquals("b".repeat(64), detail["datasetSha256"].asText())
        assertEquals(5, detail["artifactFiles"].size())
        assertEquals(1, count("SELECT count(*) FROM model_version WHERE name='tox-kcelectra' AND status='REGISTERED' AND approved_by IS NULL"))
        assertEquals(0, count("SELECT count(*) FROM outbox_event WHERE event_type='model.version.activated'"))
    }

    @Test fun `FAIL is 422 with file results in preflight and stores nothing`() {
        response = json.writeValueAsString(ModelPreflightResult("FAIL", "FILE_CHECK_FAILED",
            listOf(PreflightFileResult("model.safetensors", "FAIL", "HASH_MISMATCH"))))
        call(body()).andExpect {
            status { isUnprocessableEntity() }
            jsonPath("$.code") { value("MODEL_APPROVAL_REJECTED") }
            jsonPath("$.preflight.status") { value("FAIL") }
            jsonPath("$.preflight.files[0].file") { value("model.safetensors") }
            jsonPath("$.preflight.files[0].code") { value("HASH_MISMATCH") }
        }
        assertEquals(0, count("SELECT count(*) FROM model_version"))
        val preflight = audit("MODEL_PREFLIGHT").single()
        assertEquals(pipeline, preflight["actor_user_id"]); assertEquals("FAILURE", preflight["result"])
        assertTrue(audit("MODEL_REGISTER").isEmpty())
    }

    @Test fun `upstream error is not a registration`() {
        upstreamStatus = 500; response = "provider private detail"
        call(body()).andExpect { status { isBadGateway() }; jsonPath("$.code") { value("MODEL_PREFLIGHT_INVALID_RESPONSE") } }
        assertEquals(0, count("SELECT count(*) FROM model_version"))
    }

    @Test fun `same kind name version again is 409`() {
        call(body()).andExpect { status { isCreated() } }
        call(body()).andExpect { status { isConflict() }; jsonPath("$.code") { value("MODEL_VERSION_CONFLICT") } }
        assertEquals(1, count("SELECT count(*) FROM model_version"))
    }

    @Test fun `rule violations are rejected before preflight`() {
        listOf(body(name = "m2-klue-narrative"), body(kind = "PROMPT"), body(recommendation = null),
            body(recommendation = recommendation + ("reasons" to emptyList<String>())),
            body(registration = mapOf("source" to "PIPELINE", "datasetSha256" to "short", "artifactFiles" to files)),
            body(registration = mapOf("source" to "PIPELINE", "datasetSha256" to "b".repeat(64), "artifactFiles" to emptyList<Any>())),
        ).forEach { call(it).andExpect { status { isUnprocessableEntity() }; jsonPath("$.code") { value("MODEL_APPROVAL_REJECTED") } } }
        listOf(body(registration = null),
            body(registration = mapOf("source" to "JSON_IMPORT", "datasetSha256" to "b".repeat(64), "artifactFiles" to files)),
            body(registration = mapOf("source" to "PIPELINE", "datasetSha256" to "b".repeat(64), "artifactFiles" to files, "jsonSha256" to "c".repeat(64))),
            body() + ("approved" to true),
        ).forEach { call(it).andExpect { status { isBadRequest() } } }
        assertEquals("", received)
        assertEquals(0, count("SELECT count(*) FROM model_version"))
    }

    @Test fun `only an internal token reaches it and only ops may register`() {
        call(body(), null).andExpect { status { isUnauthorized() } }
        call(body(), "wrong-token").andExpect { status { isUnauthorized() } }
        assertTrue(InternalCallerPolicy.permits("ops", "/internal/model-versions"))
        assertTrue(InternalCallerPolicy.permits("ops", "/internal/model-versions/active"))
        listOf("ai", "scoring", "learning", "report-worker").forEach { assertFalse(InternalCallerPolicy.permits(it, "/internal/model-versions")) }
        assertEquals("", received)
    }

    @Test fun `admin public registration rejects PIPELINE source with 400`() {
        val admin = account(jdbc)
        val adminBody = body(registration = mapOf("source" to "PIPELINE"))
        mvc.post("/api/v1/admin/model-versions") {
            header("Authorization", "Bearer ${tokens.access(session(jdbc, admin))}")
            contentType = MediaType.APPLICATION_JSON; content = json.writeValueAsString(adminBody)
        }.andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        assertEquals(0, count("SELECT count(*) FROM model_version"))
    }

    companion object {
        @Volatile var response = "{}"
        @Volatile var upstreamStatus = 200
        @Volatile var received = ""
        private val upstream = HttpServer.create(InetSocketAddress("0.0.0.0", 0), 0).apply {
            createContext("/internal/models/preflight") { exchange ->
                received = exchange.requestBody.bufferedReader().readText()
                val data = response.toByteArray(); exchange.responseHeaders.add("Content-Type", "application/json")
                exchange.sendResponseHeaders(upstreamStatus, data.size.toLong()); exchange.responseBody.use { it.write(data) }
            }; start()
        }
        @JvmStatic @DynamicPropertySource fun scoring(registry: DynamicPropertyRegistry) {
            registry.add("app.services.scoring") { "http://127.0.0.1:${upstream.address.port}" }
        }
    }
}
