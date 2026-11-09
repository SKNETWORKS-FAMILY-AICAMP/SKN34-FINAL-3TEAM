package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.service.ModelPreflightRequest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals

/** Opt-in: actual scoring HTTP + disposable local S3. No deployed services or models. */
@EnabledIfEnvironmentVariable(named="PREFLIGHT_LOCAL", matches="true")
@AutoConfigureMockMvc
class ModelPreflightLocalIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var json: ObjectMapper
    @Test fun `normal hash mismatch and missing file traverse core scoring and local S3`() {
        val request = json.readValue(Files.readString(Path.of(System.getenv("PREFLIGHT_REQUEST_FILE"))), ModelPreflightRequest::class.java)
        val actor = account(jdbc); val token = tokens.access(session(jdbc, actor))
        val cases = listOf(request to "PASS",
            request.copy(files=request.files.map { if (it.file=="model.safetensors") it.copy(sha256="0".repeat(64)) else it }) to "FAIL",
            request.copy(artifactUri="s3://models/models/missing/3.0/") to "FAIL")
        cases.forEach { (body, expected) ->
            val response = mvc.post("/api/v1/admin/models/preflight") {
                header("Authorization", "Bearer $token"); contentType=MediaType.APPLICATION_JSON; content=json.writeValueAsString(body)
            }.andExpect { status { isOk() }; jsonPath("$.status") { value(expected) } }.andReturn()
            if (body !== request) {
                val expectedCode=if (body.artifactUri==request.artifactUri) "HASH_MISMATCH" else "FILE_MISSING"
                assertEquals(expectedCode,json.readTree(response.response.contentAsString)["files"].first { it["file"].asText()=="model.safetensors" }["code"].asText())
            }
        }
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MODEL_PREFLIGHT' AND result='SUCCESS'",Int::class.java,actor))
        assertEquals(2,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MODEL_PREFLIGHT' AND result='FAILURE'",Int::class.java,actor))
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM model_version",Int::class.java))
    }
    companion object {
        @JvmStatic @DynamicPropertySource fun scoring(registry: DynamicPropertyRegistry) {
            registry.add("app.services.scoring") { System.getenv("PREFLIGHT_SCORING_URL") }
            registry.add("app.internal.token") { "preflight-local-token" }
        }
    }
}
