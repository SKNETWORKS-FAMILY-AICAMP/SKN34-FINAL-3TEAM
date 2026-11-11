package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.DIVISION
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.MODEL
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.MULTIPLICATION
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.TYPES
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.UNREVIEWED
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.VERSION
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.axis
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.vectorSql
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
import kotlin.math.sqrt
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/** Actual controller -> service -> MyBatis -> pgvector responses; artifacts feed ci-contracts. */
class KnowledgeApiIntegrationTest : KnowledgePostgresTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper

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

    private fun search(vector: List<Double> = axis(), filters: Map<String, Any> = emptyMap(), k: Int = 20, minimum: Double = 0.7) =
        mapOf("vector" to vector, "embeddingModel" to MODEL, "filters" to filters, "k" to k, "minSimilarity" to minimum)

    private fun theme(semester: String = "3-1", k: Int = 3) =
        mapOf("vector" to axis(), "embeddingModel" to MODEL, "grade" to semester.take(1).toInt(), "semester" to semester,
            "k" to k, "minSimilarity" to 0.7)

    private fun learned(concepts: List<Pair<String, List<Double>>> = listOf("나눗셈" to axis()), semester: String = "3-1") =
        mapOf("concepts" to concepts.map { (text, vector) -> mapOf("text" to text, "vector" to vector) },
            "embeddingModel" to MODEL, "grade" to semester.take(1).toInt(), "semester" to semester, "minSimilarity" to 0.7)

    private fun background() {
        jdbc.update("UPDATE knowledge_chunk SET embedding=?::vector WHERE dataset_version=?", vectorSql(axis(1)), VERSION)
    }

    private fun embedding(id: String, similarity: Double = 1.0, vector: List<Double>? = null) {
        val values = vector ?: List(KnowledgeFixtures.DIMENSIONS) {
            when (it) { 0 -> similarity; 1 -> sqrt(1 - similarity * similarity); else -> 0.0 }
        }
        assertEquals(1, jdbc.update("UPDATE knowledge_chunk SET embedding=?::vector WHERE dataset_version=? AND id=?", vectorSql(values), VERSION, id))
    }

    private fun semester(code: String, value: String) {
        jdbc.update("DELETE FROM knowledge_standard_semester WHERE dataset_version=? AND standard_code=?", VERSION, code)
        jdbc.update("INSERT INTO knowledge_standard_semester VALUES (?,?,?,?)", VERSION, code, value, value.take(1).toInt())
    }

    private fun covers(code: String, content: String) {
        jdbc.update("INSERT INTO knowledge_covers VALUES (?,?,?,'TEST_REVIEWER',now()) ON CONFLICT DO NOTHING", VERSION, code, content)
    }

    private fun prerequisite(code: String, previous: String, reviewer: String = "TEST_REVIEWER") {
        jdbc.update("INSERT INTO knowledge_prerequisite VALUES (?,?,?,'synthetic regression',?,now())", VERSION, code, previous, reviewer)
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

    @Test fun `search executes pgvector cosine ranking threshold and k with stable ties`() {
        background()
        embedding("4국02-04", 1.0)
        embedding("4국02-02", 0.9)
        embedding("4수01-06", 0.8)
        val result = request("/search", search(filters = mapOf("kinds" to listOf("STANDARD")), k = 2), artifact = "search")
        assertEquals(listOf("4국02-04", "4국02-02"), result["items"].map { it["standardCode"].asText() })
        assertEquals(1.0, result["items"][0]["similarity"].asDouble(), 0.00001)
        assertEquals(0.9, result["items"][1]["similarity"].asDouble(), 0.00001)
        assertRefs(result)
        val threshold = request("/search", search(filters = mapOf("kinds" to listOf("STANDARD")), minimum = 0.85))
        assertEquals(2, threshold["items"].size())
        embedding("4국02-02", 1.0)
        val tied = request("/search", search(filters = mapOf("kinds" to listOf("STANDARD")), k = 2))
        assertEquals(listOf("4국02-02", "4국02-04"), tied["items"].map { it["standardCode"].asText() })
        val absent = request("/search", search(vector = axis(2)), artifact = "search-below-threshold")
        assertEquals("BELOW_THRESHOLD", absent["reason"].asText())
        assertEquals(0, absent["items"].size())
    }

    @Test fun `search filters use OR within fields AND between fields and array overlap`() {
        jdbc.update("UPDATE knowledge_chunk SET embedding=?::vector WHERE dataset_version=?", vectorSql(axis()), VERSION)
        jdbc.update("UPDATE knowledge_chunk SET grades='{4}', semesters='{4-2}' WHERE dataset_version=? AND id='4국02-04'", VERSION)
        val filters = mapOf("kinds" to listOf("STANDARD"), "subjects" to listOf("국어", "과학"),
            "grades" to listOf(3, 6), "semesters" to listOf("3-1", "6-2"))
        val result = request("/search", search(filters = filters))
        assertEquals(setOf("4국01-01", "4국02-02", "4과01-01", "4과01-02", "4과02-01"), result["items"].map { it["standardCode"].asText() }.toSet())
        val none = request("/search", search(filters = filters + ("semesters" to listOf("3-2"))))
        assertEquals(0, none["items"].size())
        val empty = request("/search", search(filters = mapOf("kinds" to emptyList<String>(), "grades" to emptyList<Int>())))
        assertEquals(20, empty["items"].size())
        val mixedKinds = request("/search", search(filters = mapOf("kinds" to listOf("STANDARD", "SUBJECT_GUIDE"), "subjects" to listOf("도덕"))))
        assertEquals(setOf("STANDARD", "SUBJECT_GUIDE"), mixedKinds["items"].map { it["kind"].asText() }.toSet())
    }

    @Test fun `zero threshold includes negative cosine clamped to zero across vector endpoints`() {
        jdbc.update("UPDATE knowledge_chunk SET embedding=?::vector WHERE dataset_version=?", vectorSql(axis().map { -it }), VERSION)
        val search = request("/search", search(minimum = 0.0))
        assertEquals(20, search["items"].size())
        assertTrue(search["items"].all { it["similarity"].asDouble() == 0.0 })
        val theme = request("/theme-candidates", theme() + ("minSimilarity" to 0.0))
        assertEquals(5, theme["types"].size())
        assertTrue(theme["types"].all { it["candidates"].size() > 0 })
        assertTrue(theme["types"].all { it["candidates"].all { candidate -> candidate["similarity"].asDouble() == 0.0 } })
        val learned = request("/learned", learned() + ("minSimilarity" to 0.0))["items"].single()
        assertFalse(learned["matched"].isNull)
        assertEquals(0.0, learned["matched"]["similarity"].asDouble())
    }

    @Test fun `integer JSON vectors and thresholds are numbers and omitted limits use C5 defaults`() {
        jdbc.update("UPDATE knowledge_chunk SET embedding=?::vector WHERE dataset_version=?", vectorSql(axis()), VERSION)
        val integers = List(1536) { if (it == 0) 1 else 0 }
        val common = mapOf("vector" to integers, "embeddingModel" to MODEL, "minSimilarity" to 0)
        // Integer literals are valid JSON numbers; strict parsing must only reject string coercion.
        val search = request("/search", common)
        assertEquals(5, search["items"].size())
        for (code in listOf("4국01-01", "4국02-02", "4과01-01")) {
            jdbc.update("INSERT INTO knowledge_fits VALUES (?,?,'EVALUATE','synthetic default-k regression','TEST_FIXTURE',now())", VERSION, code)
        }
        val theme = request("/theme-candidates", common + mapOf("grade" to 3, "semester" to "3-1"))
        assertEquals(3, theme["types"].single { it["thinkingType"].asText() == "EVALUATE" }["candidates"].size())
        val learned = request("/learned", mapOf("concepts" to listOf(mapOf("text" to "합성 개념", "vector" to integers)),
            "embeddingModel" to MODEL, "grade" to 3, "semester" to "3-1", "minSimilarity" to 0))
        assertFalse(learned["items"].single()["matched"].isNull)
    }

    @Test fun `subject and thinking guides ignore grade semester filters but still obey kind and thinking type`() {
        jdbc.update("UPDATE knowledge_chunk SET embedding=?::vector WHERE dataset_version=?", vectorSql(axis()), VERSION)
        val result = request("/search", search(filters = mapOf("kinds" to listOf("SUBJECT_GUIDE", "THINKING_TYPE"),
            "grades" to listOf(6), "semesters" to listOf("6-2"))))
        assertEquals(10, result["items"].size())
        val types = request("/search", search(filters = mapOf("thinkingTypes" to listOf("SOLVE", "CREATE"), "grades" to listOf(6), "semesters" to listOf("6-2"))))
        assertEquals(setOf("SOLVE", "CREATE"), types["items"].map { it["thinkingType"].asText() }.toSet())
        assertTrue(types["items"].all { it["kind"].asText() == "THINKING_TYPE" && it["subject"].isNull })
    }

    @Test fun `theme returns five types and candidates only from reviewed fits in the requested semester`() {
        jdbc.update("UPDATE knowledge_chunk SET embedding=?::vector WHERE dataset_version=?", vectorSql(axis()), VERSION)
        val result = request("/theme-candidates", theme(k = 1), artifact = "theme-candidates")
        assertEquals(TYPES.toSet(), result["types"].map { it["thinkingType"].asText() }.toSet())
        assertEquals(5, result["types"].size())
        assertTrue(result["types"].all { it["candidates"].size() == 1 && it["reason"].isNull })
        val codes = result["types"].flatMap { it["candidates"].map { c -> c["code"].asText() } }
        assertFalse("4과02-01" in codes) // REJECT fit in sample CSV
        assertFalse("4국01-01" in codes) // review decision is empty in sample CSV
        assertRefs(result)
        val empty = request("/theme-candidates", theme(semester = "3-2"), artifact = "theme-candidates-empty")
        assertEquals("BELOW_THRESHOLD", empty["reason"].asText())
        assertEquals(5, empty["types"].size())
        assertTrue(empty["types"].all { it["candidates"].size() == 0 && it["reason"].asText() == "NO_CANDIDATE" })
    }

    @Test fun `theme ranks the best of standard and confirmed covers before limiting each thinking type`() {
        background()
        embedding("4국02-04", 0.8)
        embedding("국어:초3~4:읽기:P:981aac80", 0.95)
        embedding("4국02-02", 0.9)
        jdbc.update("INSERT INTO knowledge_fits VALUES (?, '4국02-02','EVALUATE','synthetic fit','TEST_REVIEWER',now())", VERSION)
        val result = request("/theme-candidates", theme(k = 1))
        val evaluate = result["types"].single { it["thinkingType"].asText() == "EVALUATE" }
        val best = evaluate["candidates"].single()
        assertEquals("4국02-04", best["code"].asText())
        assertEquals("CONTENT", best["matchedBy"]["kind"].asText())
        assertEquals("국어:초3~4:읽기:P:981aac80", best["matchedBy"]["id"].asText())
        assertEquals(0.95, best["similarity"].asDouble(), 0.00001)
        assertEquals(2, request("/theme-candidates", theme(k = 2))["types"].single { it["thinkingType"].asText() == "EVALUATE" }["candidates"].size())
        semester("4국02-04", "3-2")
        assertEquals("4국02-02", request("/theme-candidates", theme(k = 1))["types"].single { it["thinkingType"].asText() == "EVALUATE" }["candidates"].single()["code"].asText())
    }

    @Test fun `learned returns positive future and unreviewed verdicts from actual vector and semester evidence`() {
        background()
        embedding(MULTIPLICATION, vector = axis())
        embedding(DIVISION, vector = axis(2))
        embedding(UNREVIEWED, vector = axis(3))
        semester("4수01-05", "3-2")
        semester("4수01-06", "3-2")
        val concepts = listOf("곱셈" to axis(), "나눗셈" to axis(2), "확인 전 개념" to axis(3))
        val result = request("/learned", learned(concepts), artifact = "learned")
        assertEquals(listOf("LEARNED", "NOT_YET", "HOLD"), result["items"].map { it["verdict"].asText() })
        assertEquals(listOf("곱셈", "나눗셈", "확인 전 개념"), result["items"].map { it["text"].asText() })
        assertEquals("4수01-03", result["items"][0]["learnedIn"].single()["standardCode"].asText())
        assertTrue(result["items"][1]["learnedIn"].all { it["semester"].asText() == "3-2" })
        assertEquals("NO_REVIEWED_RELATION", result["items"][2]["reason"].asText())
        assertTrue(result["reason"].isNull)
        assertRefs(result)
        val hold = request("/learned", learned(listOf("근거 없는 개념" to axis(4))), artifact = "learned-hold")
        assertEquals("HOLD", hold["items"].single()["verdict"].asText())
        assertEquals("BELOW_THRESHOLD", hold["items"].single()["reason"].asText())
        assertTrue(hold["items"].single()["matched"].isNull)
    }

    @Test fun `prerequisites from a different concept do not claim the matched concept was already learned and cycles terminate`() {
        background()
        embedding(DIVISION)
        semester("4수01-05", "4-1")
        semester("4수01-06", "4-1")
        // Earlier multiplication is a prerequisite, not evidence that division was already learned.
        prerequisite("4수01-06", "4수01-03")
        prerequisite("4수01-03", "4수01-06")
        val result = request("/learned", learned())["items"].single()
        assertEquals("NOT_YET", result["verdict"].asText())
        assertFalse(result["learnedIn"].any { it["standardCode"].asText() == "4수01-03" })
        assertEquals(2, result["learnedIn"].size())
        covers("4수01-03", DIVISION)
        val withEvidence = request("/learned", learned())["items"].single()
        assertEquals("LEARNED", withEvidence["verdict"].asText())
        assertEquals(3, withEvidence["learnedIn"].size())
    }

    @Test fun `unreviewed covers and covers without an explicit semester never infer a learned semester`() {
        background()
        embedding(DIVISION)
        jdbc.update("UPDATE knowledge_covers SET reviewed_by='' WHERE dataset_version=? AND content_id=?", VERSION, DIVISION)
        val unreviewed = request("/learned", learned())["items"].single()
        assertEquals("HOLD", unreviewed["verdict"].asText())
        assertEquals("NO_REVIEWED_RELATION", unreviewed["reason"].asText())
        jdbc.update("UPDATE knowledge_covers SET reviewed_by='TEST_REVIEWER' WHERE dataset_version=? AND content_id=?", VERSION, DIVISION)
        jdbc.update("DELETE FROM knowledge_standard_semester WHERE dataset_version=? AND standard_code IN ('4수01-05','4수01-06')", VERSION)
        val noSemester = request("/learned", learned())["items"].single()
        assertEquals("HOLD", noSemester["verdict"].asText())
        assertEquals(0, noSemester["learnedIn"].size())
        assertEquals("NO_REVIEWED_RELATION", noSemester["reason"].asText())
    }

    @Test fun `SAMPLE reviewer is never treated as an actual reviewed relation by production queries`() {
        background()
        embedding(DIVISION)
        jdbc.update("UPDATE knowledge_covers SET reviewed_by='SAMPLE' WHERE dataset_version=? AND content_id=?", VERSION, DIVISION)
        val learned = request("/learned", learned())["items"].single()
        assertEquals("HOLD", learned["verdict"].asText())
        assertEquals("NO_REVIEWED_RELATION", learned["reason"].asText())
        jdbc.update("UPDATE knowledge_fits SET reviewed_by='SAMPLE' WHERE dataset_version=? AND standard_code='4수01-06'", VERSION)
        val bundle = request("/standards", params = mapOf("codes" to "4수01-06"))["items"].single()
        assertEquals(0, bundle["covers"].size())
        assertEquals(0, bundle["fits"].size())
        embedding("4수01-06")
        val theme = request("/theme-candidates", theme())
        assertEquals(0, theme["types"].single { it["thinkingType"].asText() == "SOLVE" }["candidates"].size())
    }

    @Test fun `learned accepts twenty concepts preserving order and resolves equal similarities deterministically`() {
        background()
        embedding(DIVISION)
        embedding(MULTIPLICATION)
        val inputs = (1..20).map { "합성 개념 $it" to axis() }
        val response = request("/learned", learned(inputs))
        assertEquals(inputs.map { it.first }, response["items"].map { it["text"].asText() })
        assertEquals(20, response["items"].size())
        assertTrue(response["items"].all { it["matched"]["contentId"].asText() == listOf(DIVISION, MULTIPLICATION).min() })
    }

    @Test fun `retired and loading datasets never provide chunks or reviewed relations`() {
        background()
        embedding("4국02-04", 0.8)
        for ((version, state) in listOf("kn-20261111-02" to "RETIRED", "kn-20261111-03" to "LOADING")) {
            jdbc.update("INSERT INTO knowledge_dataset SELECT ?, ?, source, embedding_model, embedding_dimensions, chunk_count, relation_count, created_at, activated_at FROM knowledge_dataset WHERE version=?", version, state, VERSION)
            jdbc.update("""INSERT INTO knowledge_chunk SELECT ?, id,kind,subject,area,standard_code,domain_id,thinking_type,grades,semesters,notice_grade_band,
                'inactive marker',record,?::vector,content_hash,source FROM knowledge_chunk WHERE dataset_version=?""", version, vectorSql(axis()), VERSION)
            jdbc.update("INSERT INTO knowledge_covers SELECT ?,standard_code,content_id,reviewed_by,reviewed_at FROM knowledge_covers WHERE dataset_version=?", version, VERSION)
            jdbc.update("INSERT INTO knowledge_fits SELECT ?,standard_code,thinking_type,reason,reviewed_by,reviewed_at FROM knowledge_fits WHERE dataset_version=?", version, VERSION)
            jdbc.update("INSERT INTO knowledge_standard_semester SELECT ?,standard_code,semester,grade FROM knowledge_standard_semester WHERE dataset_version=?", version, VERSION)
        }
        val search = request("/search", search(filters = mapOf("kinds" to listOf("STANDARD"))))
        assertEquals(listOf("4국02-04"), search["items"].map { it["standardCode"].asText() })
        assertFalse(search.toString().contains("inactive marker"))
        val bundle = request("/standards", params = mapOf("codes" to "4국02-04"))
        assertEquals(2, bundle["items"].single()["covers"].size())
        assertEquals(1, bundle["items"].single()["fits"].size())
        assertRefs(search)
        assertRefs(bundle)
        embedding(DIVISION)
        val learned = request("/learned", learned())
        assertEquals(2, learned["items"].single()["learnedIn"].size())
        assertRefs(learned)
    }

    @Test fun `all five endpoints return explicit null dataset fallback when no dataset is active`() {
        jdbc.update("UPDATE knowledge_dataset SET status='RETIRED' WHERE version=?", VERSION)
        val responses = listOf(
            request("/standards", params = mapOf("codes" to "4국02-04"), artifact = "no-active-standards"),
            request("/thinking-types/ANALYZE", artifact = "no-active-thinking-type"),
            request("/search", search(), artifact = "no-active-search"),
            request("/theme-candidates", theme(), artifact = "no-active-theme-candidates"),
            request("/learned", learned(), artifact = "no-active-learned"),
        )
        responses.forEach {
            assertTrue(it["datasetVersion"].isNull)
            assertEquals("NO_ACTIVE_DATASET", it["reason"].asText())
        }
        assertTrue(responses[1]["guide"].isNull)
        assertEquals(0, responses[2]["items"].size())
    }

    @Test fun `all endpoints enforce internal token and SYSTEM role`() {
        val calls = listOf("/standards" to null, "/thinking-types/ANALYZE" to null,
            "/search" to search(), "/theme-candidates" to theme(), "/learned" to learned())
        for ((endpoint, body) in calls) {
            val params = if (endpoint == "/standards") mapOf("codes" to "4국02-04") else emptyMap()
            val unauthorized = request(endpoint, body, params, expected = 401, token = null,
                artifact = if (endpoint == "/standards") "unauthenticated" else null)
            assertEquals("UNAUTHENTICATED", unauthorized["code"].asText())
            for (role in listOf("PARENT", "STUDENT", "ADMIN", "CONTENT")) {
                val forbidden = request(endpoint, body, params, expected = 403, role = role,
                    artifact = if (endpoint == "/standards" && role == "PARENT") "forbidden" else null)
                assertEquals("FORBIDDEN", forbidden["code"].asText())
            }
        }
        assertEquals("UNAUTHENTICATED", request("/thinking-types/ANALYZE", expected = 401, token = "wrong")["code"].asText())
        assertEquals("FORBIDDEN", request("/thinking-types/ANALYZE", expected = 403, role = null)["code"].asText())
    }

    @Test fun `bad models and vector dimensions are conflicts for all vector endpoints`() {
        for ((endpoint, body) in listOf("/search" to search(), "/theme-candidates" to theme(), "/learned" to learned())) {
            val model = request(endpoint, body + ("embeddingModel" to "wrong-model"), expected = 409,
                artifact = if (endpoint == "/search") "embedding-mismatch" else null)
            assertEquals("KNOWLEDGE_EMBEDDING_MISMATCH", model["code"].asText())
            val short = if (endpoint == "/learned") body + ("concepts" to listOf(mapOf("text" to "개념", "vector" to listOf(1.0, 0.0))))
                else body + ("vector" to listOf(1.0, 0.0))
            assertEquals("KNOWLEDGE_EMBEDDING_MISMATCH", request(endpoint, short, expected = 409)["code"].asText())
        }
    }

    @Test fun `query and body limits enum membership semester ownership and empty inputs are validation errors`() {
        val badQueries = listOf(emptyMap(), mapOf("codes" to ""), mapOf("codes" to (1..11).joinToString(",") { "code$it" }),
            mapOf("codes" to "4국02-04", "grade" to "2"), mapOf("codes" to "4국02-04", "grade" to "3.5"),
            mapOf("codes" to "4국02-04", "thinkingType" to "UNKNOWN"))
        badQueries.forEach { assertEquals("VALIDATION_FAILED", request("/standards", params = it, expected = 400)["code"].asText()) }
        request("/thinking-types/UNKNOWN", expected = 400)
        val invalidSearch = listOf(
            search() + ("k" to 0), search() + ("k" to 21), search() + ("minSimilarity" to -0.1), search() + ("minSimilarity" to 1.1),
            search() + ("vector" to emptyList<Double>()), search() + ("vector" to List(1536) { 0.0 }),
            search() + ("embeddingModel" to " "), search(filters = mapOf("kinds" to listOf("UNKNOWN"))),
            search(filters = mapOf("subjects" to listOf("영어"))), search(filters = mapOf("grades" to listOf(2))),
            search(filters = mapOf("semesters" to listOf("3-3"))), search(filters = mapOf("thinkingTypes" to listOf("UNKNOWN"))),
        )
        invalidSearch.forEachIndexed { i, body ->
            assertEquals("VALIDATION_FAILED", request("/search", body, expected = 400, artifact = if (i == 0) "invalid-request" else null)["code"].asText())
        }
        listOf(theme() + ("k" to 11), theme() + ("grade" to 2), theme() + ("semester" to "4-1"), theme() + ("semester" to "3-3"))
            .forEach { request("/theme-candidates", it, expected = 400) }
        listOf(learned(emptyList()), learned((1..21).map { "$it" to axis() }), learned(listOf(" " to axis())),
            learned() + ("semester" to "4-1")).forEach { request("/learned", it, expected = 400) }
    }

    @Test fun `unknown fields coercion nulls and nonfinite vector entries never bypass C5 validation`() {
        val bodies = listOf(
            search() + ("studentId" to "must-not-be-accepted"), search() + ("k" to 1.5), search() + ("k" to "1"),
            search() + ("embeddingModel" to 123),
            search() + ("filters" to mapOf("studentId" to "must-not-be-accepted")),
            search() + ("filters" to mapOf("grades" to listOf("3"))), search() + ("vector" to listOf("1")),
            search() + ("k" to null), search() + ("minSimilarity" to null), search() + ("filters" to null),
            search() + ("filters" to mapOf("kinds" to null)), search() + ("vector" to listOf(null)),
        )
        bodies.forEach { request("/search", it, expected = 400) }
        request("/theme-candidates", theme() + ("grade" to "3"), expected = 400)
        request("/learned", learned() + ("concepts" to listOf(mapOf("text" to "개념", "vector" to axis(), "studentId" to "invalid"))), expected = 400)
        request("/learned", learned() + ("concepts" to listOf(mapOf("text" to 123, "vector" to axis()))), expected = 400)
        for (invalid in listOf("NaN", "Infinity", "-Infinity", "1e999")) {
            request("/search", """{"vector":[$invalid],"embeddingModel":"$MODEL"}""", expected = 400)
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
