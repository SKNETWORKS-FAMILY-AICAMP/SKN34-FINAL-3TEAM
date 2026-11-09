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

    @Test fun `theme draft and image usage are stored and listed by call type with token-less images unpriced`() {
        val (_, access) = adminToken()
        fun record(callType: String, input: Int?, output: Int?) = usage.record(com.sagomungchi.core._common.messaging.EventEnvelope(type = "llm.usage.recorded",
            source = "ai-service", dataschema = "llm.usage.recorded.v1", data = com.sagomungchi.core.usage.domain.LlmUsageRecorded(
                "ai", callType, "no-price", "theme-draft@1", input, output, 1200, true, null, OffsetDateTime.parse("2041-01-01T12:00:00+09:00"))))
        record("THEME_DRAFT", 100, 200); record("THEME_IMAGE", null, null); record("THEME_IMAGE", null, null)
        mvc.get("/api/v1/admin/ai-usage?from=2041-01-01&to=2041-01-01&callType=THEME_IMAGE") { header("Authorization", "Bearer $access") }.andExpect {
            status { isOk() }; jsonPath("$.items.length()") { value(1) }; jsonPath("$.items[0].callType") { value("THEME_IMAGE") }
            jsonPath("$.items[0].calls") { value(2) }; jsonPath("$.items[0].unpricedCalls") { value(2) }
            jsonPath("$.items[0].costUsd") { value(org.hamcrest.Matchers.nullValue()) }
        }
        mvc.get("/api/v1/admin/ai-usage?from=2041-01-01&to=2041-01-01") { header("Authorization", "Bearer $access") }
            .andExpect { status { isOk() }; jsonPath("$.items[*].callType") { value(org.hamcrest.Matchers.containsInAnyOrder("THEME_DRAFT", "THEME_IMAGE")) } }
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
    private fun registerHttp(access: String, body: Any) = mvc.post("/api/v1/admin/model-versions") {
        header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON
        content = json.writeValueAsString(body)
    }

    @Test fun `JSON import preserves limitations provenance actor and does not activate`() {
        val (actor, access) = adminToken()
        val command = registration().copy(
            evaluation = evidence().copy(limitations = listOf("임시 경계이며 품질 승인 아님")),
            registration = com.sagomungchi.core.admin.domain.RegistrationMetadata(
                com.sagomungchi.core.admin.domain.RegistrationSource.JSON_IMPORT,
                "a".repeat(64), "b".repeat(64), listOf("artifactUri", "evaluation.limitations"),
                listOf(com.sagomungchi.core.admin.domain.RegistrationArtifact("config.json", 123, "c".repeat(64)))))
        val result = registerHttp(access, command).andExpect {
            status { isCreated() }; jsonPath("$.status") { value("REGISTERED") }
            jsonPath("$.evalResult.evidence.limitations[0]") { value("임시 경계이며 품질 승인 아님") }
            jsonPath("$.evalResult.activeScopes.length()") { value(0) }
        }.andReturn().response.contentAsString
        val id = UUID.fromString(json.readTree(result)["id"].asText())
        val detail = json.readTree(jdbc.queryForObject("SELECT detail::text FROM audit_log WHERE target_id=? AND action='MODEL_REGISTER'", String::class.java, id))
        assertEquals("JSON_IMPORT", detail["source"].asText())
        assertEquals("a".repeat(64), detail["jsonSha256"].asText())
        assertEquals("b".repeat(64), detail["manifestSha256"].asText())
        assertEquals("c".repeat(64), detail["artifactFiles"][0]["sha256"].asText())
        assertEquals("artifactUri", detail["modifiedFields"][0].asText())
        assertEquals(actor, jdbc.queryForObject("SELECT actor_user_id FROM audit_log WHERE target_id=?", UUID::class.java, id))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, id.toString()))
        registerHttp(access, command.copy(evaluation = evidence())).andExpect { status { isConflict() }; jsonPath("$.code") { value("MODEL_VERSION_CONFLICT") } }
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE target_id=?", Int::class.java, id))
        mvc.get("/api/v1/admin/model-versions") { header("Authorization", "Bearer $access") }
            .andExpect { status { isOk() }; jsonPath("$.items[?(@.id == '$id')].evalResult.evidence.limitations[0]") { value(org.hamcrest.Matchers.hasItem("임시 경계이며 품질 승인 아님")) } }
    }

    @Test fun `old manual requests and stored evidence default to empty limitations`() {
        val (_, access) = adminToken()
        val body = json.valueToTree<com.fasterxml.jackson.databind.node.ObjectNode>(registration())
        body.remove("registration")
        (body["evaluation"] as com.fasterxml.jackson.databind.node.ObjectNode).remove("limitations")
        val result = registerHttp(access, body).andExpect { status { isCreated() }; jsonPath("$.evalResult.evidence.limitations.length()") { value(0) } }.andReturn().response.contentAsString
        val id = UUID.fromString(json.readTree(result)["id"].asText())
        jdbc.update("UPDATE model_version SET eval_result=eval_result #- '{evidence,limitations}' WHERE id=?", id)
        assertTrue(service.list(null, 0, 100).items.single { it.id == id }.evalResult!!.evidence.limitations.isEmpty())
        assertEquals("MANUAL", jdbc.queryForObject("SELECT detail->>'source' FROM audit_log WHERE target_id=?", String::class.java, id))
    }

    @Test fun `MODEL requires artifact URI and invalid provenance has no registration side effects`() {
        val (_, access) = adminToken()
        val valid = json.valueToTree<com.fasterxml.jackson.databind.node.ObjectNode>(registration())
        val before = jdbc.queryForObject("SELECT count(*) FROM model_version", Int::class.java)
        val invalidBodies = listOf(
            valid.deepCopy().putNull("artifactUri"), valid.deepCopy().put("artifactUri", " "),
            valid.deepCopy().set<com.fasterxml.jackson.databind.node.ObjectNode>("registration", json.readTree("""{"source":"JSON_IMPORT","jsonSha256":"bad"}""")),
            valid.deepCopy().set<com.fasterxml.jackson.databind.node.ObjectNode>("registration", json.readTree("""{"source":"MANUAL","jsonSha256":"${"a".repeat(64)}"}""")),
            valid.deepCopy().apply { (get("evaluation") as com.fasterxml.jackson.databind.node.ObjectNode).putArray("limitations").addNull() })
        invalidBodies.forEach { registerHttp(access, it).andExpect { status { isUnprocessableEntity() }; jsonPath("$.code") { value("MODEL_APPROVAL_REJECTED") } } }
        assertEquals(before, jdbc.queryForObject("SELECT count(*) FROM model_version", Int::class.java))
    }

    @Test fun `registration rejects approval fields and unknown nested fields`() {
        val (_, access) = adminToken()
        listOf("approved", "scopes", "reason", "reanalysisPlanned", "approvedBy", "unexpected").forEach { field ->
            val body = json.valueToTree<com.fasterxml.jackson.databind.node.ObjectNode>(registration()).put(field, "forbidden")
            registerHttp(access, body).andExpect { status { isBadRequest() } }
        }
        val body = json.valueToTree<com.fasterxml.jackson.databind.node.ObjectNode>(registration())
        (body["evaluation"] as com.fasterxml.jackson.databind.node.ObjectNode).put("approved", true)
        registerHttp(access, body).andExpect { status { isBadRequest() } }
    }

    @Test fun `manifest metadata rejects missing bytes invalid paths and duplicate files`() {
        val (_, access) = adminToken()
        fun request() = json.valueToTree<com.fasterxml.jackson.databind.node.ObjectNode>(registration()).apply {
            set<com.fasterxml.jackson.databind.node.ObjectNode>("registration", json.readTree("""{
                "source":"JSON_IMPORT","jsonSha256":"${"a".repeat(64)}","manifestSha256":"${"b".repeat(64)}",
                "artifactFiles":[{"file":"config.json","bytes":123,"sha256":"${"c".repeat(64)}"}]}"""))
        }
        for (missing in listOf(true, false)) {
            val body = request()
            val file = body["registration"]["artifactFiles"][0] as com.fasterxml.jackson.databind.node.ObjectNode
            if (missing) file.remove("bytes") else file.putNull("bytes")
            registerHttp(access, body).andExpect { status { isBadRequest() } }
        }
        val traversal = request()
        (traversal["registration"]["artifactFiles"][0] as com.fasterxml.jackson.databind.node.ObjectNode).put("file", "../config.json")
        registerHttp(access, traversal).andExpect { status { isUnprocessableEntity() } }
        val duplicates = request()
        val files = duplicates["registration"]["artifactFiles"] as com.fasterxml.jackson.databind.node.ArrayNode
        files.add(files[0].deepCopy<com.fasterxml.jackson.databind.JsonNode>())
        registerHttp(access, duplicates).andExpect { status { isUnprocessableEntity() } }
    }

}
