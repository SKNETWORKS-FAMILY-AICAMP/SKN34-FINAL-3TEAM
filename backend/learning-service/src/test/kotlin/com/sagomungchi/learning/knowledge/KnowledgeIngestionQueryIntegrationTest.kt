package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.learning.knowledge.client.FakeKnowledgeEmbedder
import com.sagomungchi.learning.knowledge.domain.KnowledgeChunks
import com.sagomungchi.learning.knowledge.domain.RelationReview
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * Real #466 admin HTTP/loader/V14 -> #469 query HTTP integration.
 * Only embedding is fake-bigram-v1 over public samples. TEST_FIXTURE is synthetic test data,
 * never real relation approval; the original SAMPLE review file remains unchanged.
 */
class KnowledgeIngestionQueryIntegrationTest : KnowledgePostgresTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper

    private val admin = "/internal/admin/knowledge/datasets"
    private val query = "/internal/knowledge"
    private val code = "4국02-04"
    private val fake = FakeKnowledgeEmbedder()

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
        assertEquals("14", jdbc.queryForObject("SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank DESC LIMIT 1", String::class.java))
    }

    private fun load(records: List<JsonNode> = KnowledgeSamples.records,
        reviews: List<RelationReview> = KnowledgeFixtures.syntheticReviews()): JsonNode =
        http(HttpMethod.POST, admin, mapOf(
            "source" to KnowledgeSamples.dataset["source"].deepCopy<ObjectNode>().put("syntheticIntegrationTest", true),
            "records" to records, "reviews" to reviews,
        ), expected = 201)

    private fun activate(version: String) = http(HttpMethod.POST, "$admin/$version/activate", emptyMap<String, Any>())

    private fun vectorFor(id: String): List<Float> {
        val chunk = KnowledgeChunks.fromRecords(KnowledgeSamples.records).single { it.id == id }
        return fake.vector(chunk.text).toList()
    }

    private fun fiveQueries(): List<JsonNode> {
        val vector = vectorFor(code)
        return listOf(
            http(HttpMethod.GET, "$query/standards", params = mapOf("codes" to code, "grade" to "3", "thinkingType" to "EVALUATE")),
            http(HttpMethod.GET, "$query/thinking-types/EVALUATE"),
            http(HttpMethod.POST, "$query/search", mapOf("vector" to vector, "embeddingModel" to fake.model,
                "k" to 5, "minSimilarity" to 0.99, "filters" to mapOf("kinds" to listOf("STANDARD")))),
            http(HttpMethod.POST, "$query/theme-candidates", mapOf("vector" to vector, "embeddingModel" to fake.model,
                "grade" to 3, "semester" to "3-1", "minSimilarity" to 0.7)),
            http(HttpMethod.POST, "$query/learned", mapOf("concepts" to listOf(mapOf(
                "text" to "샘플 나눗셈 내용 요소", "vector" to vectorFor(KnowledgeFixtures.DIVISION))),
                "embeddingModel" to fake.model, "grade" to 3, "semester" to "3-1", "minSimilarity" to 0.99)),
        )
    }

    private fun assertCurrent(version: String): List<JsonNode> {
        val responses = fiveQueries()
        responses.forEach { response ->
            assertEquals(version, response["datasetVersion"].asText())
            assertTrue(response["reason"].isNull)
            assertReferences(response, version)
        }
        val bundle = responses[0]["items"].single()
        assertEquals(code, bundle["standard"]["code"].asText())
        assertEquals(2, bundle["covers"].size())
        assertEquals("EVALUATE", bundle["fits"].single()["thinkingType"].asText())
        assertEquals("EVALUATE", responses[1]["guide"]["type"].asText())
        assertEquals(code, responses[2]["items"][0]["standardCode"].asText())
        assertEquals(KnowledgeFixtures.TYPES.toSet(), responses[3]["types"].map { it["thinkingType"].asText() }.toSet())
        assertTrue(responses[3]["types"].single { it["thinkingType"].asText() == "EVALUATE" }["candidates"]
            .any { it["code"].asText() == code })
        val learned = responses[4]["items"].single()
        assertEquals("LEARNED", learned["verdict"].asText())
        assertEquals(KnowledgeFixtures.DIVISION, learned["matched"]["contentId"].asText())
        assertEquals(setOf("4수01-05", "4수01-06"), learned["learnedIn"].map { it["standardCode"].asText() }.toSet())
        return responses
    }

    private fun assertReferences(node: JsonNode, version: String) {
        if (node.isObject && node.has("kind") && node.has("id") && node.has("datasetVersion")) {
            assertEquals(version, node["datasetVersion"].asText())
        }
        node.elements().forEachRemaining { if (it.isContainerNode) assertReferences(it, version) }
    }

    @Test fun `real V14 admin load is invisible until activation then supplies all five knowledge APIs`() {
        emptyKnowledge()
        val loaded = load()
        val dataset = loaded["dataset"]
        val version = dataset["version"].asText()
        assertEquals("LOADING", dataset["status"].asText())
        assertEquals(FakeKnowledgeEmbedder.MODEL, dataset["embeddingModel"].asText())
        assertEquals(215, dataset["chunkCount"].asInt())
        assertTrue(loaded["embeddingRequests"].asInt() > 0)
        assertTrue(loaded["previousVersion"].isNull)
        fiveQueries().forEach {
            assertTrue(it["datasetVersion"].isNull)
            assertEquals("NO_ACTIVE_DATASET", it["reason"].asText())
        }
        assertEquals("ACTIVE", activate(version)["status"].asText())
        assertCurrent(version)
        assertEquals(listOf("TEST_FIXTURE"), jdbc.queryForList(
            "SELECT DISTINCT reviewed_by FROM knowledge_covers WHERE dataset_version=?", String::class.java, version))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM knowledge_chunk WHERE dataset_version=? AND embedding IS NULL", Int::class.java, version))
    }

    @Test fun `real reloading reuses embeddings and activation changes every query version without stale guidance`() {
        emptyKnowledge()
        val first = load()
        val firstVersion = first["dataset"]["version"].asText()
        activate(firstVersion)
        assertCurrent(firstVersion)

        val repeated = load()
        val repeatedVersion = repeated["dataset"]["version"].asText()
        assertNotEquals(firstVersion, repeatedVersion)
        assertEquals(firstVersion, repeated["previousVersion"].asText())
        assertEquals(first["dataset"]["chunks"], repeated["dataset"]["chunks"])
        assertEquals(first["dataset"]["relations"], repeated["dataset"]["relations"])
        assertEquals(215, repeated["reusedEmbeddings"].asInt())
        assertEquals(0, repeated["embeddingRequests"].asInt())
        assertCurrent(firstVersion) // LOADING data must not replace the active response.
        activate(repeatedVersion)
        assertEquals("RETIRED", http(HttpMethod.GET, "$admin/$firstVersion")["status"].asText())
        assertCurrent(repeatedVersion)

        // Team-authored sample guidance can change without changing the official standard statement.
        val changedRecords = KnowledgeSamples.records.map { record ->
            if (record["kind"].asText() == "thinking_type" && record["type"].asText() == "EVALUATE")
                record.deepCopy<ObjectNode>().put("name", "새 판 시험용 따져 보기")
            else record
        }
        val changed = load(changedRecords, emptyList()) // Carries only the synthetic fixture relations.
        val changedVersion = changed["dataset"]["version"].asText()
        assertEquals(repeatedVersion, changed["previousVersion"].asText())
        assertEquals(214, changed["reusedEmbeddings"].asInt())
        assertEquals(1, changed["embeddingRequests"].asInt())
        activate(changedVersion)
        val responses = assertCurrent(changedVersion)
        assertEquals("새 판 시험용 따져 보기", responses[1]["guide"]["name"].asText())
        assertEquals("새 판 시험용 따져 보기", responses[0]["thinkingType"]["name"].asText())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM knowledge_dataset WHERE status='ACTIVE'", Int::class.java))
    }
}
