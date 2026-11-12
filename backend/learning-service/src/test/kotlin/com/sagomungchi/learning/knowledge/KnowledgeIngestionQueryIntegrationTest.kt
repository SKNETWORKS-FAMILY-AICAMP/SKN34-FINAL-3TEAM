package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.learning.knowledge.domain.RelationReview
import com.sagomungchi.learning.knowledge.service.KnowledgeService
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/** #466 실제 적재·활성화 → #469 HTTP/서비스 조회. 외부 임베딩 호출 없이 V17 DB에서 실행한다. */
class KnowledgeIngestionQueryIntegrationTest : KnowledgePostgresTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var service: KnowledgeService
    private val admin = "/internal/admin/knowledge/datasets"
    private val query = "/internal/knowledge"
    private val code = "4국02-04"

    private fun http(method: HttpMethod, path: String, body: Any? = null, expected: Int = 200,
        params: Map<String, String> = emptyMap()): JsonNode {
        val builder = request(method, path).header("X-Internal-Token", "knowledge-test-token")
            .header("X-User-Role", "SYSTEM")
        params.forEach { (name, value) -> builder.param(name, value) }
        body?.let { builder.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(it)) }
        val response = mvc.perform(builder).andExpect(status().`is`(expected)).andReturn().response
        return json.readTree(response.getContentAsString(Charsets.UTF_8))
    }

    private fun emptyKnowledge() {
        jdbc.execute("TRUNCATE knowledge_dataset,knowledge_chunk,knowledge_standard_semester,knowledge_fits,knowledge_covers,knowledge_prerequisite")
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM flyway_schema_history WHERE success AND version='17'", Int::class.java))
        assertEquals(0, jdbc.queryForObject("""
            SELECT count(*) FROM information_schema.columns WHERE table_schema='public'
              AND ((table_name='knowledge_chunk' AND column_name='embedding')
                OR (table_name='knowledge_dataset' AND column_name IN ('embedding_model','embedding_dimensions')))
        """.trimIndent(), Int::class.java))
    }

    private fun load(records: List<JsonNode> = KnowledgeSamples.records,
        reviews: List<RelationReview> = KnowledgeFixtures.syntheticReviews()): JsonNode =
        http(HttpMethod.POST, admin, mapOf(
            "source" to KnowledgeSamples.dataset["source"].deepCopy<ObjectNode>().put("localIntegrationTest", true),
            "records" to records, "reviews" to reviews,
        ), expected = 201)
    private fun activate(version: String) = http(HttpMethod.POST, "$admin/$version/activate", emptyMap<String, Any>())
    private fun twoQueries() = listOf(
        http(HttpMethod.GET, "$query/standards", params = mapOf("codes" to code, "grade" to "3", "thinkingType" to "EVALUATE")),
        http(HttpMethod.GET, "$query/thinking-types/EVALUATE"),
    )
    private fun assertCurrent(version: String): List<JsonNode> {
        val responses = twoQueries()
        responses.forEach {
            assertEquals(version, it["datasetVersion"].asText())
            assertTrue(it["reason"].isNull)
            assertReferences(it, version)
        }
        val bundle = responses[0]["items"].single()
        assertEquals(code, bundle["standard"]["code"].asText())
        assertEquals(2, bundle["covers"].size())
        assertEquals("EVALUATE", bundle["fits"].single()["thinkingType"].asText())
        assertEquals("EVALUATE", responses[1]["guide"]["type"].asText())
        return responses
    }
    private fun assertReferences(node: JsonNode, version: String) {
        if (node.isObject && node.has("kind") && node.has("id") && node.has("datasetVersion"))
            assertEquals(version, node["datasetVersion"].asText())
        node.elements().forEachRemaining { if (it.isContainerNode) assertReferences(it, version) }
    }

    @Test fun `V17 admin load is invisible until activation then supplies both code APIs`() {
        emptyKnowledge()
        val loaded = load()
        val dataset = loaded["dataset"]
        val version = dataset["version"].asText()
        assertEquals("LOADING", dataset["status"].asText())
        assertEquals(215, dataset["chunkCount"].asInt())
        assertFalse(dataset.has("embeddingModel"))
        assertFalse(loaded.has("embeddingRequests"))
        twoQueries().forEach {
            assertTrue(it["datasetVersion"].isNull)
            assertEquals("NO_ACTIVE_DATASET", it["reason"].asText())
        }
        assertEquals("ACTIVE", activate(version)["status"].asText())
        assertCurrent(version)
    }

    @Test fun `reloading carries reviewed relations and activation switches both query versions`() {
        emptyKnowledge()
        val firstVersion = load()["dataset"]["version"].asText()
        activate(firstVersion)
        assertCurrent(firstVersion)
        val records = KnowledgeSamples.records.map { record ->
            if (record["kind"].asText() == "thinking_type" && record["type"].asText() == "EVALUATE")
                record.deepCopy<ObjectNode>().put("name", "새 판 시험용 따져 보기") else record
        }
        val changed = load(records, emptyList())
        val next = changed["dataset"]["version"].asText()
        assertNotEquals(firstVersion, next)
        assertEquals(firstVersion, changed["previousVersion"].asText())
        assertCurrent(firstVersion)
        activate(next)
        assertEquals("RETIRED", http(HttpMethod.GET, "$admin/$firstVersion")["status"].asText())
        val responses = assertCurrent(next)
        assertEquals("새 판 시험용 따져 보기", responses[1]["guide"]["name"].asText())
        assertEquals("새 판 시험용 따져 보기", responses[0]["thinkingType"]["name"].asText())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM knowledge_dataset WHERE status='ACTIVE'", Int::class.java))
    }

    @Test fun `actual curriculum supports five code examples all types and grade checks under two seconds`() {
        emptyKnowledge()
        val records = Files.readAllLines(Path.of("../../scripts/knowledge/data/curriculum-v1.jsonl"), Charsets.UTF_8)
            .filter { it.isNotBlank() }.map { json.readTree(it) }
        assertEquals(1341, records.size)
        val loaded = load(records, emptyList())
        val version = loaded["dataset"]["version"].asText()
        assertEquals(1341, loaded["dataset"]["chunkCount"].asInt())
        activate(version)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM knowledge_fits", Int::class.java))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM knowledge_covers", Int::class.java))
        val observations = mutableListOf<Map<String, Any>>()
        fun measured(label: String, path: String, params: Map<String, String> = emptyMap()): JsonNode {
            val start = System.nanoTime()
            val response = http(HttpMethod.GET, path, params = params)
            val elapsed = TimeUnit.NANOSECONDS.toMicros(System.nanoTime() - start) / 1000.0
            observations += mapOf("case" to label, "latencyMs" to elapsed, "response" to response)
            assertTrue(elapsed < 2000, "$label exceeded two seconds: ${elapsed}ms")
            assertEquals(version, response["datasetVersion"].asText())
            assertReferences(response, version)
            return response
        }
        val codes = listOf("4국02-04", "4수01-06", "4과01-01", "4사01-01", "4도01-01")
        val standards = records.filter { it["kind"].asText() == "standard" }.associateBy { it["code"].asText() }
        codes.forEach { selected ->
            val original = standards.getValue(selected)
            val grade = original["grades"].first().asInt()
            val params = mapOf("codes" to selected, "grade" to grade.toString(), "thinkingType" to "EVALUATE")
            val result = measured("code:$selected", "$query/standards", params)
            val item = result["items"].single()
            assertEquals(original["statement"], item["standard"]["statement"])
            assertEquals(original["explanation"], item["standard"]["explanation"])
            assertTrue(item["gradeMatch"].asBoolean())
            assertTrue(result["reason"].isNull)
            assertEquals(0, item["fits"].size())
            assertEquals(0, item["covers"].size())
            assertFalse(item["domain"].isNull)
            assertTrue(result["subjectGuides"].size() > 0)
            assertEquals(json.valueToTree<JsonNode>(service.standards(listOf(selected), grade, "EVALUATE")), result)
            val mismatch = measured("grade-mismatch:$selected", "$query/standards", params + ("grade" to "6"))
            assertFalse(mismatch["items"].single()["gradeMatch"].asBoolean())
        }
        KnowledgeFixtures.TYPES.forEach { type ->
            val response = measured("type:$type", "$query/thinking-types/$type")
            assertEquals(type, response["guide"]["type"].asText())
            assertTrue(response["guide"]["questionMust"].size() > 0)
        }
        val artifact = Path.of("build/contracts/knowledge-actual-observations.json")
        Files.createDirectories(artifact.parent)
        Files.writeString(artifact, json.writerWithDefaultPrettyPrinter().writeValueAsString(mapOf(
            "datasetVersion" to version, "recordCount" to records.size, "reviewedRelationCount" to 0,
            "source" to "scripts/knowledge/data/curriculum-v1.jsonl", "queries" to observations,
        )), Charsets.UTF_8)
    }
}
