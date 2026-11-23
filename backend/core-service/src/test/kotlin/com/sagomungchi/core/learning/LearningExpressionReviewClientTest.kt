package com.sagomungchi.core.learning

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.client.LearningExpressionReviewClient
import com.sagomungchi.core.learning.domain.ExpressionReview
import com.sagomungchi.core.learning.domain.ExpressionReviewLabel
import com.sagomungchi.core.learning.domain.ExpressionReviewPage
import com.sagomungchi.core.learning.domain.ExpressionReviewSource
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.*

/** learning 표현 검토 요청·응답 해석 (api-spec 2.8·4.1.5, #907). 실제 HTTP */
class LearningExpressionReviewClientTest {
    private val stub = LearningHttpStub()
    private val json = jacksonObjectMapper()
    private val admin = UUID.randomUUID()
    private val review = UUID.randomUUID()
    private val context = UserContext(admin.toString(), "ADMIN", setOf(UUID.randomUUID().toString()), null)
    private lateinit var client: LearningExpressionReviewClient

    @BeforeEach fun setUp() {
        val props = AppProperties(AppProperties.Internal("synthetic-internal", Duration.ofSeconds(1), Duration.ofSeconds(1)),
            services = mapOf("learning" to stub.url))
        // 서킷(최근 20건)이 열리지 않게 호출 묶음마다 새로 만든다
        client = LearningExpressionReviewClient(
            LearningClient(InternalRestClientFactory(props, RestClient.builder()), LearningHttpProperties(Duration.ofSeconds(1))), json)
        UserContextHolder.set(context)
    }

    @AfterEach fun tearDown() { UserContextHolder.clear(); stub.close() }

    private fun item(vararg changed: Pair<String, Any?>) = linkedMapOf<String, Any?>("id" to review.toString(), "source" to "GRAY_ZONE",
        "text" to "합성 답변 글", "modelVersion" to null, "label" to null, "labeledAt" to null,
        "createdAt" to "2026-11-21T00:00:00.123456789Z") + changed
    private fun page(vararg items: Map<String, Any?>) = json.writeValueAsString(
        mapOf("items" to items.toList(), "page" to 0, "size" to 20, "totalElements" to items.size))
    private fun reply(status: Int, body: String) { stub.respond = { LearningHttpStub.Reply(status, body) } }
    private fun list() = client.list(false, null, 0, 20)
    private fun label() = client.label(review, ExpressionReviewLabel.CLEAN)
    private fun fails(status: Int, code: String, call: () -> Any) {
        val error = assertFailsWith<BusinessException> { call() }
        assertEquals(status, error.status.value()); assertEquals(code, error.code)
        assertEquals(context, UserContextHolder.currentOrNull()) // 실패해도 컨텍스트 복구
    }

    @Test fun `list sends the admin with an empty student scope and maps only the contract fields`() {
        val second = UUID.randomUUID()
        reply(200, page(item("studentId" to "secret-student", "studentName" to "secret-name"),
            item("id" to second.toString(), "source" to "COMMUNITY_REPORT", "modelVersion" to "tox:1", "label" to "SKIP",
                "labeledAt" to "2026-11-22T09:00:00+09:00")))
        val found = client.list(true, ExpressionReviewSource.COMMUNITY_REPORT, 1, 5)

        assertEquals(ExpressionReviewPage(listOf(
            ExpressionReview(review, ExpressionReviewSource.GRAY_ZONE, "합성 답변 글", null, null, null, "2026-11-21T00:00:00.123456789Z"),
            ExpressionReview(second, ExpressionReviewSource.COMMUNITY_REPORT, "합성 답변 글", "tox:1", ExpressionReviewLabel.SKIP,
                "2026-11-22T09:00:00+09:00", "2026-11-21T00:00:00.123456789Z")), 0, 20, 2), found)
        val sent = stub.requests.single()
        assertEquals("/internal/admin/expression-reviews?labeled=true&source=COMMUNITY_REPORT&page=1&size=5", sent.target)
        assertEquals("ADMIN", sent.header("X-User-Role")); assertEquals(admin.toString(), sent.header("X-User-Id"))
        assertNull(sent.header("X-Student-Scope"))
        assertEquals(context, UserContextHolder.currentOrNull())
        assertFalse(json.writeValueAsString(found).contains("secret"))
    }

    @Test fun `a successful list outside the contract is 502`() {
        val broken = listOf("id", "source", "text", "modelVersion", "label", "labeledAt", "createdAt").map { page(item() - it) } +
            listOf(item("id" to "not-uuid"), item("id" to 1), item("source" to "OTHER"), item("text" to 1), item("text" to null),
                item("modelVersion" to 1), item("label" to "BAD"), item("labeledAt" to "어제"), item("createdAt" to "2026-11-21"),
                item("createdAt" to null)).map { page(it) } +
            listOf("", "not json", "[]", "{}", """{"items":{}}""", """{"items":[1],"page":0,"size":20,"totalElements":1}""",
                page().replace(""""page":0""", """"page":-1"""), page().replace(""""size":20""", """"size":"20""""),
                page().replace(""""totalElements":0""", """"totalElements":0.5"""))
        broken.forEach { body ->
            reply(200, body)
            fails(502, "LEARNING_INVALID_RESPONSE", ::list)
        }
        reply(201, page()) // 200만 계약
        fails(502, "LEARNING_INVALID_RESPONSE", ::list)
    }

    @Test fun `list errors are not shape errors`() {
        reply(400, """{"code":"VALIDATION_FAILED"}""")
        fails(400, "VALIDATION_FAILED", ::list)
        for (status in listOf(401, 403, 404, 409, 500, 503)) {
            reply(status, """{"code":"EXPRESSION_REVIEW_NOT_FOUND"}""")
            fails(503, "LEARNING_UNAVAILABLE", ::list)
        }
    }

    @Test fun `label sends only the label and returns the typed item`() {
        reply(200, json.writeValueAsString(item("label" to "CLEAN", "labeledAt" to "2026-11-22T00:00:00Z")))
        val saved = label()
        assertEquals(review, saved.id); assertEquals(ExpressionReviewLabel.CLEAN, saved.label)
        val sent = stub.requests.single()
        assertEquals("PUT", sent.method); assertEquals("/internal/admin/expression-reviews/$review/label", sent.target)
        assertEquals("""{"label":"CLEAN"}""", sent.body); assertNull(sent.header("X-Student-Scope"))
        assertEquals(context, UserContextHolder.currentOrNull())
    }

    @Test fun `label separates shape errors, rejections and failures`() {
        for (body in listOf("", "[]", "{}", json.writeValueAsString(item("label" to "BAD")))) {
            reply(200, body)
            fails(502, "LEARNING_INVALID_RESPONSE", ::label)
        }
        reply(202, json.writeValueAsString(item("label" to "CLEAN")))
        fails(502, "LEARNING_INVALID_RESPONSE", ::label)
        reply(404, """{"code":"EXPRESSION_REVIEW_NOT_FOUND"}""")
        fails(404, "EXPRESSION_REVIEW_NOT_FOUND", ::label)
        reply(400, "{}")
        fails(400, "VALIDATION_FAILED", ::label)
        for ((status, body) in listOf(404 to """{"code":"NOT_FOUND"}""", 404 to "broken", 409 to "{}", 500 to "{}")) {
            reply(status, body)
            fails(503, "LEARNING_UNAVAILABLE", ::label)
        }
    }

    @Test fun `no context means no call`() {
        UserContextHolder.clear()
        assertEquals(403, assertFailsWith<BusinessException> { list() }.status.value())
        assertTrue(stub.requests.isEmpty())
    }
}
