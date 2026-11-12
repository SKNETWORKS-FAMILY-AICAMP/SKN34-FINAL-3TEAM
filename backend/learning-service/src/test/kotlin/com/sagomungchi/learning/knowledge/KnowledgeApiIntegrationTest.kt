package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.TYPES
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.UNREVIEWED
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.VERSION
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/** Actual controller -> service -> MyBatis -> PostgreSQL responses; artifacts feed ci-contracts. */
class KnowledgeApiIntegrationTest : KnowledgePostgresTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var service: com.sagomungchi.learning.knowledge.service.KnowledgeService

    private val base = "/internal/knowledge"

    private fun request(
        endpoint: String, body: Any? = null, params: Map<String, String> = emptyMap(),
        expected: Int = 200, token: String? = "knowledge-test-token", role: String? = "SYSTEM",
        artifact: String? = null,
    ): JsonNode {
        val builder = MockMvcRequestBuilders.request(if (body == null) HttpMethod.GET else HttpMethod.POST, base + endpoint)
        token?.let { builder.header("X-Internal-Token", it) }
        role?.let { builder.header("X-User-Role", it) }
        // Deliberately no X-Student-Scope: these APIs must not need any student identity.
        params.forEach { (key, value) -> builder.param(key, value) }
        if (body != null) builder.contentType(MediaType.APPLICATION_JSON)
            .content(if (body is String) body else json.writeValueAsString(body))
        val result = mvc.perform(builder).andExpect(status().`is`(expected)).andReturn()
        val text = result.response.getContentAsString(Charsets.UTF_8)
        artifact?.let {
            val file = Path.of("build", "contracts", "knowledge", "$it.json")
            Files.createDirectories(file.parent)
            Files.writeString(file, text, Charsets.UTF_8)
        }
        return json.readTree(text)
    }

    private fun assertRefs(value: JsonNode, version: String = VERSION) {
        if (value.isObject && value.has("datasetVersion") && value.has("kind") && value.has("id")) {
            assertEquals(version, value["datasetVersion"].asText())
            assertTrue(value["id"].asText().isNotBlank())
        }
        value.elements().forEachRemaining { if (it.isContainerNode) assertRefs(it, version) }
    }

    @Test fun `standards returns original statements distinct subject guides reviewed covers and refs`() {
        val response = request("/standards", params = mapOf("codes" to "4국02-04,4국02-02,4과01-01,missing", "grade" to "3", "thinkingType" to "EVALUATE"), artifact = "standards")
        assertEquals(VERSION, response["datasetVersion"].asText())
        assertTrue(response["reason"].isNull)
        assertEquals(listOf("missing"), response["missingCodes"].map { it.asText() })
        assertEquals(3, response["items"].size())
        assertEquals(setOf("국어", "과학"), response["subjectGuides"].map { it["subject"].asText() }.toSet())
        assertEquals(2, response["subjectGuides"].size())
        val korean = response["items"].single { it["standard"]["code"].asText() == "4국02-04" }
        assertEquals("글에 나타난 사실과 의견을 구분하고 필자와 자신의 의견을 비교한다.", korean["standard"]["statement"].asText())
        assertTrue(korean["gradeMatch"].asBoolean())
        assertEquals("EVALUATE", korean["fits"].single()["thinkingType"].asText())
        assertEquals(2, korean["covers"].size())
        val science = response["items"].single { it["standard"]["code"].asText() == "4과01-01" }
        assertEquals("과학:초3~4:힘과 우리 생활", science["domain"]["id"].asText())
        assertEquals(1, science["covers"].size())
        assertTrue(science["covers"].all { it["domainId"].asText() == "과학:초3~4:운동과 에너지" })
        assertEquals("EVALUATE", response["thinkingType"]["type"].asText())
        assertRefs(response)
    }

    @Test fun `standards preserves nulls when grade or related records are absent and gives missing reason`() {
        jdbc.update("UPDATE knowledge_chunk SET domain_id='missing-domain', record=jsonb_set(record,'{explanation}','null'::jsonb) WHERE dataset_version=? AND id='4국02-04'", VERSION)
        val result = request("/standards", params = mapOf("codes" to "4국02-04"))
        val item = result["items"].single()
        assertTrue(item["gradeMatch"].isNull)
        assertTrue(item["domain"].isNull)
        assertTrue(item["standard"]["explanation"].isNull)
        assertTrue(result["thinkingType"].isNull)
        val mismatch = request("/standards", params = mapOf("codes" to "4국02-04", "grade" to "6"))
        assertFalse(mismatch["items"].single()["gradeMatch"].asBoolean())
        val missing = request("/standards", params = mapOf("codes" to "missing"), artifact = "standards-missing")
        assertEquals("CODE_NOT_FOUND", missing["reason"].asText())
        assertEquals(0, missing["items"].size())
        assertEquals(listOf("missing"), missing["missingCodes"].map { it.asText() })
    }

    @Test fun `thinking type guides are available to SYSTEM without student scope`() {
        for (type in TYPES) {
            val result = request("/thinking-types/$type", artifact = if (type == "ANALYZE") "thinking-type" else null)
            assertEquals(type, result["guide"]["type"].asText())
            assertTrue(result["guide"]["basis"].size() > 0)
            assertTrue(result["guide"]["elements"].size() > 0)
            assertTrue(result["guide"]["questionMust"].size() > 0)
            assertTrue(result["reason"].isNull)
            assertRefs(result)
        }
    }

    @Test fun `direct service methods return the exact controller DTOs for mission drafts`() {
        val codes = listOf("4국02-04", "4과01-01", "missing")
        val direct = service.standards(codes, 3, "EVALUATE")
        val http = request("/standards", params = mapOf("codes" to codes.joinToString(","), "grade" to "3", "thinkingType" to "EVALUATE"))
        assertEquals(json.valueToTree<JsonNode>(direct), http)
        assertEquals(json.valueToTree<JsonNode>(service.thinkingType("EVALUATE")), request("/thinking-types/EVALUATE"))
        kotlin.test.assertFailsWith<com.sagomungchi.learning._common.exception.BusinessException> {
            service.standards(emptyList(), 3, null)
        }
    }

    @Test fun `missing or unreviewed relations return empty arrays without dropping the standard`() {
        jdbc.update("UPDATE knowledge_fits SET reviewed_by='SAMPLE'")
        jdbc.update("UPDATE knowledge_covers SET reviewed_by='SAMPLE'")
        val response = request("/standards", params = mapOf("codes" to "4국02-04"), artifact = "standards-empty-relations")
        val item = response["items"].single()
        assertEquals(0, item["fits"].size())
        assertEquals(0, item["covers"].size())
        assertFalse(item["domain"].isNull)
        assertTrue(response["reason"].isNull)
        jdbc.update("DELETE FROM knowledge_fits")
        jdbc.update("DELETE FROM knowledge_covers")
        assertEquals(response, request("/standards", params = mapOf("codes" to "4국02-04")))
    }

    @Test fun `retired and loading datasets never supply code lookup results`() {
        for (state in listOf("LOADING", "RETIRED")) {
            jdbc.update("UPDATE knowledge_dataset SET status=? WHERE version=?", state, VERSION)
            for (response in listOf(
                request("/standards", params = mapOf("codes" to "4국02-04"), artifact = "no-active-standards"),
                request("/thinking-types/ANALYZE", artifact = "no-active-thinking-type"),
            )) {
                assertTrue(response["datasetVersion"].isNull)
                assertEquals("NO_ACTIVE_DATASET", response["reason"].asText())
            }
        }
    }

    @Test fun `missing thinking type is an explicit code not found response`() {
        jdbc.update("DELETE FROM knowledge_fits WHERE thinking_type='ANALYZE'")
        jdbc.update("DELETE FROM knowledge_chunk WHERE kind='THINKING_TYPE' AND id='ANALYZE'")
        val response = request("/thinking-types/ANALYZE", artifact = "thinking-type-missing")
        assertEquals("CODE_NOT_FOUND", response["reason"].asText())
        assertTrue(response["guide"].isNull)
    }

    @Test fun `both endpoints enforce token and SYSTEM role without student identity`() {
        for (endpoint in listOf("/standards", "/thinking-types/ANALYZE")) {
            val params = if (endpoint == "/standards") mapOf("codes" to "4국02-04") else emptyMap()
            assertEquals("UNAUTHENTICATED", request(endpoint, params = params, expected = 401, token = null,
                artifact = if (endpoint == "/standards") "unauthenticated" else null)["code"].asText())
            for (role in listOf("PARENT", "STUDENT", "ADMIN", "CONTENT")) {
                assertEquals("FORBIDDEN", request(endpoint, params = params, expected = 403, role = role,
                    artifact = if (endpoint == "/standards" && role == "PARENT") "forbidden" else null)["code"].asText())
            }
        }
        request("/thinking-types/ANALYZE", expected = 401, token = "wrong")
        request("/thinking-types/ANALYZE", expected = 403, role = null)
    }

    @Test fun `code limits grade and thinking type are validated`() {
        val invalid = listOf(emptyMap(), mapOf("codes" to ""), mapOf("codes" to "4국02-04,"),
            mapOf("codes" to (1..11).joinToString(",") { "code$it" }),
            mapOf("codes" to "4국02-04", "grade" to "2"), mapOf("codes" to "4국02-04", "grade" to "7"),
            mapOf("codes" to "4국02-04", "grade" to "3.5"), mapOf("codes" to "4국02-04", "thinkingType" to "UNKNOWN"))
        invalid.forEach { assertEquals("VALIDATION_FAILED", request("/standards", params = it, expected = 400,
            artifact = "invalid-request")["code"].asText()) }
        request("/thinking-types/UNKNOWN", expected = 400)
        val codes = List(10) { "4국02-04" }
        assertEquals(10, request("/standards", params = mapOf("codes" to codes.joinToString(",")))["items"].size())
    }

    @Test fun `removed vector routes are not exposed`() {
        for (endpoint in listOf("/search", "/theme-candidates", "/learned")) {
            request(endpoint, body = emptyMap<String, Any>(), expected = 404)
        }
    }

    @Test fun `sample modify and unreviewed relation decisions are preserved without inventing evidence`() {
        val result = request("/standards", params = mapOf("codes" to "4과02-01,4국01-01"))
        val science = result["items"].single { it["standard"]["code"].asText() == "4과02-01" }
        val ids = science["covers"].map { it["id"].asText() }
        assertTrue("과학:초3~4:생명:K:82d3d210" in ids)
        assertFalse("과학:초3~4:생명:K:a046b0ee" in ids)
        assertEquals(0, science["fits"].size())
        val korean = result["items"].single { it["standard"]["code"].asText() == "4국01-01" }
        assertFalse(korean["covers"].any { it["id"].asText() == UNREVIEWED })
        assertEquals(0, korean["fits"].size())
        assertNotNull(jdbc.queryForObject("SELECT extversion FROM pg_extension WHERE extname='vector'", String::class.java))
    }
}
