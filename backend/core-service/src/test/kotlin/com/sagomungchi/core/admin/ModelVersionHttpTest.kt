package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.service.*
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders
import org.springframework.test.web.servlet.result.MockMvcResultMatchers
import java.net.URI
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

@AutoConfigureMockMvc
class ModelVersionHttpTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var service: ModelVersionService
    @Autowired lateinit var usage: com.sagomungchi.core.usage.service.LlmUsageService
    private fun adminToken(permission: String? = "SERVICE_OPS"): Pair<UUID, String> {
        val user = account(jdbc, permission = permission)
        return user to tokens.access(session(jdbc, user))
    }
    private fun studentToken(): String {
        val user = account(jdbc, "PARENT", null); consents(jdbc, user)
        val id = UUID.randomUUID(); val now = OffsetDateTime.now()
        jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'테스트',3,2017,false,'ACTIVE',?,?)", id, now, now)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',?)", UUID.randomUUID(), user, id, now)
        consents(jdbc, user, id)
        return tokens.access(session(jdbc, user, "STUDENT", id))
    }

    @Test fun `parent student and non SERVICE_OPS admins receive 403 for every registry and usage operation`() {
        val parent = account(jdbc, "PARENT", null); consents(jdbc, parent)
        val denied = listOf(tokens.access(session(jdbc, parent, "PARENT")), studentToken(), adminToken(null).second, adminToken("CONTENT").second,
            adminToken("PAYMENT_VIEW").second, adminToken("PAYMENT_REFUND").second)
        denied.forEach { token ->
            listOf("/api/v1/admin/model-versions", "/api/v1/admin/ai-usage?from=2026-11-01&to=2026-11-02").forEach { path ->
                mvc.get(path) { header("Authorization", "Bearer $token") }.andExpect { status { isForbidden() }; jsonPath("$.code") { value("FORBIDDEN") } }
            }
            listOf("/api/v1/admin/model-versions", "/api/v1/admin/model-versions/${UUID.randomUUID()}/activate",
                "/api/v1/admin/model-versions/${UUID.randomUUID()}/rollback").forEach { path ->
                mvc.post(path) { header("Authorization", "Bearer $token"); contentType = MediaType.APPLICATION_JSON; content = "{}" }
                    .andExpect { status { isForbidden() }; jsonPath("$.code") { value("FORBIDDEN") } }
            }
        }
    }

    @Test fun `matrix parameter and percent-encoded admin paths are authorized like the plain path`() {
        val parent = account(jdbc, "PARENT", null); consents(jdbc, parent)
        val token = tokens.access(session(jdbc, parent, "PARENT"))
        listOf("/api/v1/admin;x/ai-usage?from=2026-11-01&to=2026-11-02", "/api/v1/%61dmin/ai-usage?from=2026-11-01&to=2026-11-02",
            "/api/v1/admin;x/model-versions").forEach { path ->
            mvc.perform(MockMvcRequestBuilders.get(URI.create(path)).header("Authorization", "Bearer $token"))
                .andExpect(MockMvcResultMatchers.status().isForbidden)
                .andExpect(MockMvcResultMatchers.jsonPath("$.code").value("FORBIDDEN"))
        }
    }

    @Test fun `SERVICE_OPS HTTP registration activation rollback and internal snapshot use authenticated actors`() {
        val (actor, access) = adminToken()
        val command = registration()
        fun register(version: String): String = mvc.post("/api/v1/admin/model-versions") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
            content = json.writeValueAsString(command.copy(version = version))
        }.andExpect { status { isCreated() }; jsonPath("$.status") { value("REGISTERED") } }
            .andReturn().response.contentAsString.let { json.readTree(it)["id"].asText() }
        val first = register("v1"); val second = register("v2")
        listOf(first, second).forEach { id ->
            mvc.post("/api/v1/admin/model-versions/$id/activate") {
                header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
                content = json.writeValueAsString(approval())
            }.andExpect { status { isOk() }; jsonPath("$.approvedBy") { value(actor.toString()) } }
        }
        mvc.post("/api/v1/admin/model-versions/$first/rollback") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
            content = json.writeValueAsString(RollbackVersion(listOf(SCOPE_A), "복귀", false))
        }.andExpect { status { isOk() }; jsonPath("$.evalResult.revision") { value(3) } }
        mvc.get("/api/v1/admin/model-versions") {
            header("Authorization", "Bearer $access"); param("kind", "MODEL"); param("size", "1")
        }.andExpect { status { isOk() }; jsonPath("$.items.length()") { value(1) }; jsonPath("$.size") { value(1) } }
        mvc.get("/internal/model-versions/active") { header("X-Internal-Token", "repository-test-token") }.andExpect {
            status { isOk() }; jsonPath("$.items[0].id") { value(first) }; jsonPath("$.items[0].scopes[0]") { value(SCOPE_A) }
            jsonPath("$.items[0].evalResult") { doesNotExist() }; jsonPath("$.items[0].approvedBy") { doesNotExist() }
        }
        mvc.get("/api/v1/admin/ai-usage?from=2026-12-01&to=2026-12-01") { header("Authorization", "Bearer $access") }
            .andExpect { status { isOk() }; jsonPath("$.items.length()") { value(0) } }
    }

    @Test fun `usage HTTP returns the selected period failures latency tokens and null cost`() {
        val (_, access) = adminToken()
        usage.record(com.sagomungchi.core._common.messaging.EventEnvelope(type = "llm.usage.recorded", source = "ai-service",
            dataschema = "llm.usage.recorded.v1", data = com.sagomungchi.core.usage.domain.LlmUsageRecorded(
                "ai", "FOLLOWUP", "no-price", "followup@1", 10, 20, 300, false, "TIMEOUT", OffsetDateTime.parse("2040-01-01T12:00:00+09:00"))))
        mvc.get("/api/v1/admin/ai-usage?from=2040-01-01&to=2040-01-01&callType=FOLLOWUP") {
            header("Authorization", "Bearer $access")
        }.andExpect {
            status { isOk() }; jsonPath("$.period.from") { value("2040-01-01") }; jsonPath("$.period.to") { value("2040-01-01") }
            jsonPath("$.items[0].calls") { value(1) }; jsonPath("$.items[0].failures") { value(1) }
            jsonPath("$.items[0].latencyMs") { value(300.0) }; jsonPath("$.items[0].inputTokens") { value(10) }
            jsonPath("$.items[0].outputTokens") { value(20) }; jsonPath("$.items[0].unpricedCalls") { value(1) }
            jsonPath("$.items[0].costUsd") { value(org.hamcrest.Matchers.nullValue()) }
        }
    }

    @Test fun `usage HTTP allows 366 days but rejects excess periods and unsupported years with 400`() {
        val (_, access) = adminToken()
        mvc.get("/api/v1/admin/ai-usage") {
            header("Authorization", "Bearer $access"); param("from", "2024-01-01"); param("to", "2024-12-31")
        }.andExpect { status { isOk() }; jsonPath("$.period.to") { value("2024-12-31") } }
        listOf("2024-01-01" to "2025-01-01", "0001-01-01" to "9999-12-31",
            "0000-01-01" to "0001-01-01", "9999-12-31" to "+10000-01-01",
            "-999999999-01-01" to "+999999999-12-31").forEach { (from, to) ->
            mvc.get("/api/v1/admin/ai-usage") {
                header("Authorization", "Bearer $access"); param("from", from); param("to", to)
            }.andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        }
    }

    @Test fun `null entries in registration activation and rollback scopes return 422 and preserve state`() {
        val (actor, access) = adminToken()
        val request = json.readTree(json.writeValueAsString(registration())) as com.fasterxml.jackson.databind.node.ObjectNode
        (request["evaluation"] as com.fasterxml.jackson.databind.node.ObjectNode).putArray("evaluatedScopes").add(SCOPE_A).addNull()
        mvc.post("/api/v1/admin/model-versions") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
            content = json.writeValueAsString(request)
        }.andExpect { status { isUnprocessableEntity() }; jsonPath("$.code") { value("MODEL_APPROVAL_REJECTED") } }
        val first = service.register(registration(), actor)
        mvc.post("/api/v1/admin/model-versions/${first.id}/activate") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
            content = """{"approved":true,"scopes":["$SCOPE_A",null],"reason":"승인","reanalysisPlanned":false}"""
        }.andExpect { status { isUnprocessableEntity() }; jsonPath("$.code") { value("MODEL_APPROVAL_REJECTED") } }
        assertEquals("REGISTERED", jdbc.queryForObject("SELECT status FROM model_version WHERE id=?", String::class.java, first.id))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, first.id.toString()))
        service.activate(first.id, approval(), actor)
        val second = service.register(registration(first.name, "v2"), actor)
        service.activate(second.id, approval(), actor)
        mvc.post("/api/v1/admin/model-versions/${first.id}/rollback") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
            content = """{"scopes":["$SCOPE_A",null],"reason":"복귀","reanalysisPlanned":false}"""
        }.andExpect { status { isUnprocessableEntity() }; jsonPath("$.code") { value("MODEL_APPROVAL_REJECTED") } }
        assertEquals(second.id, service.active().single { it.name == first.name }.id)
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject IN (?,?)", Int::class.java, first.id.toString(), second.id.toString()))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE target_id=? AND action='MODEL_ROLLBACK'", Int::class.java, first.id))
    }

    @Test fun `internal token is required and invalid parameters and missing decisions fail explicitly`() {
        val (actor, access) = adminToken(); val target = service.register(registration(), actor)
        mvc.get("/internal/model-versions/active").andExpect { status { isUnauthorized() } }
        mvc.get("/internal/model-versions/active") { header("X-Internal-Token", "wrong") }.andExpect { status { isUnauthorized() } }
        mvc.get("/internal/model-versions/active") { header("Authorization", "Bearer $access") }.andExpect { status { isUnauthorized() } }
        mvc.get("/api/v1/admin/model-versions").andExpect { status { isUnauthorized() } }
        listOf("/api/v1/admin/model-versions?kind=UNKNOWN", "/api/v1/admin/model-versions?page=-1",
            "/api/v1/admin/model-versions?size=101", "/api/v1/admin/ai-usage?from=2026-11-02&to=2026-11-01",
            "/api/v1/admin/ai-usage?from=2026-11-01&to=2026-11-02&callType=UNKNOWN",
            "/api/v1/admin/ai-usage?from=invalid&to=2026-11-02").forEach { path ->
            mvc.get(path) { header("Authorization", "Bearer $access") }.andExpect { status { isBadRequest() } }
        }
        mvc.post("/api/v1/admin/model-versions/${target.id}/activate") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
            content = """{"scopes":["$SCOPE_A"],"reason":"승인"}"""
        }.andExpect { status { isBadRequest() } }
        mvc.post("/api/v1/admin/model-versions/${target.id}/activate") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
            content = json.writeValueAsString(approval().copy(approved = false))
        }.andExpect { status { isUnprocessableEntity() } }
    }
}
