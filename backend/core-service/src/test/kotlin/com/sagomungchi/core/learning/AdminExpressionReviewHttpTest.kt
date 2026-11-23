package com.sagomungchi.core.learning

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.admin.repository.MissionAuditRepository
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers
import org.mockito.Mockito
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.put
import java.util.UUID
import kotlin.test.*

/** 관리자 표현 검토 → learning 중계·감사 (FN-ADM-24, api-spec 2.8·4.1.5, #728) */
@AutoConfigureMockMvc
/** 라벨 감사는 learning에 넘기기 전에 커밋돼야 해서(stub이 다른 스레드에서 확인) 시험 트랜잭션으로 묶지 않음. 감사는 이 시험의 관리자 것만 센다 */
class AdminExpressionReviewHttpTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @MockitoSpyBean lateinit var auditRows: MissionAuditRepository

    private val review = UUID.randomUUID()
    private val student = UUID.randomUUID()
    private fun item(label: String? = null) = linkedMapOf("id" to review.toString(), "source" to "GRAY_ZONE", "text" to "합성 답변 글",
        "modelVersion" to "tox-kcelectra:1.0-1119", "label" to label, "labeledAt" to label?.let { "2026-11-22T00:00:00Z" },
        "createdAt" to "2026-11-21T00:00:00Z")
    private fun page(vararg items: Map<String, Any?>) = json.writeValueAsString(mapOf("items" to items.toList(), "page" to 0, "size" to 20, "totalElements" to items.size))
    private fun token(permission: String? = "SERVICE_OPS"): Pair<UUID, String> {
        val user = account(jdbc, permission = permission)
        return user to tokens.access(session(jdbc, user))
    }
    private fun audits(action: String, actor: UUID) = jdbc.queryForList(
        "SELECT actor_user_id, target_type, target_id, result, detail::text AS detail FROM audit_log WHERE action=? AND actor_user_id=? ORDER BY created_at", action, actor)

    @BeforeEach fun reset() { stub.reset() }

    @Test fun `list forwards as admin with empty student scope, returns allowlisted fields only and audits shown ids`() {
        val (admin, access) = token()
        val leaked = item() + mapOf("studentId" to student.toString(), "answerId" to UUID.randomUUID().toString(), "studentName" to "secret")
        stub.respond = { LearningHttpStub.Reply(body = page(leaked)) }
        val body = mvc.get("/api/v1/admin/expression-reviews?labeled=true&source=GRAY_ZONE&page=1&size=5") { header("Authorization", "Bearer $access") }
            .andExpect { status { isOk() }; jsonPath("$.items[0].id") { value(review.toString()) }; jsonPath("$.items[0].text") { value("합성 답변 글") }
                jsonPath("$.totalElements") { value(1) } }
            .andReturn().response.getContentAsString(Charsets.UTF_8)
        assertEquals(json.readTree(page(item())), json.readTree(body)) // 계약 7칸 그대로, null도 칸으로
        assertFalse(body.contains(student.toString())); assertFalse(body.contains("studentName")); assertFalse(body.contains("answerId"))
        val seen = stub.requests.single()
        assertEquals("GET", seen.method)
        assertEquals("/internal/admin/expression-reviews?labeled=true&source=GRAY_ZONE&page=1&size=5", seen.target)
        assertEquals("ADMIN", seen.header("X-User-Role")); assertEquals(admin.toString(), seen.header("X-User-Id")); assertNull(seen.header("X-Student-Scope"))
        val view = audits("EXPRESSION_REVIEW_VIEW", admin).single()
        assertEquals(admin, view["actor_user_id"]); assertEquals("EXPRESSION_REVIEW", view["target_type"]); assertEquals("SUCCESS", view["result"])
        val detail = json.readTree(view["detail"] as String)
        assertEquals(listOf(review.toString()), detail["reviewIds"].map { it.asText() })
        assertFalse((view["detail"] as String).contains("합성 답변 글"))
    }

    @Test fun `list defaults and an empty page is still audited`() {
        val (admin, access) = token()
        stub.respond = { LearningHttpStub.Reply(body = page()) }
        mvc.get("/api/v1/admin/expression-reviews") { header("Authorization", "Bearer $access") }
            .andExpect { status { isOk() }; jsonPath("$.items.length()") { value(0) } }
        assertEquals("/internal/admin/expression-reviews?labeled=false&page=0&size=20", stub.requests.single().target)
        assertEquals(0, json.readTree(audits("EXPRESSION_REVIEW_VIEW", admin).single()["detail"] as String)["reviewIds"].size())
    }

    @Test fun `bad list query is 400 without calling learning, a malformed learning page is 502 and a learning error is 503, all without audit`() {
        val (admin, access) = token()
        listOf("?source=OTHER", "?size=0", "?size=101", "?page=-1", "?labeled=maybe").forEach {
            mvc.get("/api/v1/admin/expression-reviews$it") { header("Authorization", "Bearer $access") }.andExpect { status { isBadRequest() } }
        }
        assertTrue(stub.requests.isEmpty())
        listOf(page(item() + ("source" to "OTHER")), page(item() + ("id" to "not-uuid")), """{"items":{}}""", "[]").forEach { bad ->
            stub.respond = { LearningHttpStub.Reply(body = bad) }
            mvc.get("/api/v1/admin/expression-reviews") { header("Authorization", "Bearer $access") }
                .andExpect { status { isBadGateway() }; jsonPath("$.code") { value("LEARNING_INVALID_RESPONSE") } }
        }
        for (failed in listOf(404, 500)) {
            stub.respond = { LearningHttpStub.Reply(status = failed, body = "{}", headers = mapOf("Content-Type" to "application/problem+json")) }
            mvc.get("/api/v1/admin/expression-reviews") { header("Authorization", "Bearer $access") }
                .andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("LEARNING_UNAVAILABLE") } }
        }
        stub.respond = { LearningHttpStub.Reply(status = 400, body = "{}") }
        mvc.get("/api/v1/admin/expression-reviews") { header("Authorization", "Bearer $access") }
            .andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        assertTrue(audits("EXPRESSION_REVIEW_VIEW", admin).isEmpty())
    }

    @Test fun `label is audited once before forwarding`() {
        val (admin, access) = token()
        stub.respond = {
            assertEquals(1, audits("EXPRESSION_REVIEW_LABEL", admin).size) // 감사를 남긴 뒤 전달 (api-spec 4.1.5)
            LearningHttpStub.Reply(body = json.writeValueAsString(item("OFFENSIVE") + ("studentId" to student.toString())))
        }
        val body = mvc.put("/api/v1/admin/expression-reviews/$review/label") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON; content = """{"label":"OFFENSIVE"}"""
        }.andExpect { status { isOk() }; jsonPath("$.label") { value("OFFENSIVE") }; jsonPath("$.id") { value(review.toString()) } }
            .andReturn().response.getContentAsString(Charsets.UTF_8)
        assertEquals(json.valueToTree<JsonNode>(item("OFFENSIVE")), json.readTree(body))
        assertFalse(body.contains(student.toString()))
        val seen = stub.requests.single()
        assertEquals("PUT", seen.method); assertEquals("/internal/admin/expression-reviews/$review/label", seen.target)
        assertEquals("""{"label":"OFFENSIVE"}""", seen.body); assertEquals(admin.toString(), seen.header("X-User-Id"))
        val labeled = audits("EXPRESSION_REVIEW_LABEL", admin).single()
        assertEquals(admin, labeled["actor_user_id"]); assertEquals(review, labeled["target_id"]); assertEquals("EXPRESSION_REVIEW", labeled["target_type"])
        val detail = json.readTree(labeled["detail"] as String)
        assertEquals(listOf("label"), detail.fieldNames().asSequence().toList()); assertEquals("OFFENSIVE", detail["label"].asText())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE action LIKE 'EXPRESSION_REVIEW_LABEL_%' AND actor_user_id=?", Int::class.java, admin))
    }

    @Test fun `bad label body is 400 before any audit or call`() {
        val (admin, access) = token()
        listOf("""{"label":"BAD"}""", """{}""", """{"label":null}""", """{"label":"CLEAN","extra":1}""", "[]", "not json",
            "", "null", "\"CLEAN\"", """{"label":0}""", """{"label":["CLEAN"]}""").forEach {
            mvc.put("/api/v1/admin/expression-reviews/$review/label") {
                header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON; content = it
            }.andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        }
        mvc.put("/api/v1/admin/expression-reviews/not-a-uuid/label") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON; content = """{"label":"CLEAN"}"""
        }.andExpect { status { isBadRequest() } }
        assertTrue(stub.requests.isEmpty())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE action LIKE 'EXPRESSION_REVIEW%' AND actor_user_id=?", Int::class.java, admin))
    }

    @Test fun `learning 404 is not found and unexpected answers are unknown, each send audited once`() {
        val (admin, access) = token()
        fun send() = mvc.put("/api/v1/admin/expression-reviews/$review/label") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON; content = """{"label":"CLEAN"}"""
        }
        stub.respond = { LearningHttpStub.Reply(404, """{"code":"EXPRESSION_REVIEW_NOT_FOUND","status":404}""", mapOf("Content-Type" to "application/problem+json")) }
        send().andExpect { status { isNotFound() }; jsonPath("$.code") { value("EXPRESSION_REVIEW_NOT_FOUND") } }
        stub.respond = { LearningHttpStub.Reply(body = json.writeValueAsString(item("OFFENSIVE"))) } // 보낸 라벨과 다름
        send().andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("LEARNING_UNAVAILABLE") } }
        stub.respond = { LearningHttpStub.Reply(500, "{}", mapOf("Content-Type" to "application/problem+json")) }
        send().andExpect { status { isServiceUnavailable() } }
        assertEquals(3, audits("EXPRESSION_REVIEW_LABEL", admin).size)
    }

    @Test fun `malformed label answer is 502 and an unknown result is 503, both with the audit id`() {
        val (admin, access) = token()
        fun send() = mvc.put("/api/v1/admin/expression-reviews/$review/label") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON; content = """{"label":"CLEAN"}"""
        }
        val cases = listOf(
            Triple(200, "[]", 502 to "LEARNING_INVALID_RESPONSE"),
            Triple(200, json.writeValueAsString(item("CLEAN") + ("createdAt" to "어제")), 502 to "LEARNING_INVALID_RESPONSE"),
            Triple(200, json.writeValueAsString(item("CLEAN") + ("id" to UUID.randomUUID().toString())), 503 to "LEARNING_UNAVAILABLE"),
            Triple(200, json.writeValueAsString(item("SKIP")), 503 to "LEARNING_UNAVAILABLE"),
            Triple(500, "{}", 503 to "LEARNING_UNAVAILABLE"),
        )
        val details = cases.map { (answered, body, expected) ->
            stub.respond = { LearningHttpStub.Reply(answered, body) }
            val response = send().andExpect { status { isEqualTo(expected.first) }; jsonPath("$.code") { value(expected.second) } }
                .andReturn().response.getContentAsString(Charsets.UTF_8)
            json.readTree(response)["detail"].asText()
        }
        val operations = jdbc.queryForList("SELECT id FROM audit_log WHERE action='EXPRESSION_REVIEW_LABEL' AND actor_user_id=?", UUID::class.java, admin)
        assertEquals(cases.size, operations.size) // 보낼 때마다 한 줄
        assertEquals(operations.map { it.toString() }.toSet(),
            details.map { it.substringAfter("확인 번호: ").substringBefore('.') }.toSet())
    }

    @Test fun `failed audit hides the list and never forwards a label`() {
        val (admin, access) = token()
        stub.respond = { LearningHttpStub.Reply(body = page(item())) }
        Mockito.doThrow(IllegalStateException("audit down")).`when`(auditRows).insert(
            ArgumentMatchers.any(UUID::class.java) ?: admin, ArgumentMatchers.eq(admin) ?: admin,
            ArgumentMatchers.anyString(), ArgumentMatchers.anyString(), ArgumentMatchers.nullable(UUID::class.java),
            ArgumentMatchers.anyString(), ArgumentMatchers.anyMap<String, Any?>() ?: emptyMap())
        val listed = mvc.get("/api/v1/admin/expression-reviews") { header("Authorization", "Bearer $access") }
            .andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("EXPRESSION_REVIEW_AUDIT_UNAVAILABLE") } }
            .andReturn().response.getContentAsString(Charsets.UTF_8)
        assertFalse(listed.contains("합성 답변 글"))
        mvc.put("/api/v1/admin/expression-reviews/$review/label") {
            header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON; content = """{"label":"CLEAN"}"""
        }.andExpect { status { isServiceUnavailable() }; jsonPath("$.code") { value("EXPRESSION_REVIEW_AUDIT_UNAVAILABLE") } }
        assertEquals(listOf("GET"), stub.requests.map { it.method })
    }

    @Test fun `only SERVICE_OPS administrators reach it`() {
        for (permission in listOf(null, "CONTENT", "PAYMENT_VIEW")) {
            val (_, access) = token(permission)
            mvc.get("/api/v1/admin/expression-reviews") { header("Authorization", "Bearer $access") }.andExpect { status { isForbidden() } }
            mvc.put("/api/v1/admin/expression-reviews/$review/label") {
                header("Authorization", "Bearer $access"); contentType = MediaType.APPLICATION_JSON; content = """{"label":"CLEAN"}"""
            }.andExpect { status { isForbidden() } }
        }
        mvc.get("/api/v1/admin/expression-reviews").andExpect { status { isUnauthorized() } }
        assertTrue(stub.requests.isEmpty())
    }

    companion object {
        private val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
        @JvmStatic @AfterAll fun close() { stub.close() }
    }
}
