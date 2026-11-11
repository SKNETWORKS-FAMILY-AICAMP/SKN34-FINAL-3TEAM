package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.knowledge.KnowledgeFixtures.Companion.VERSION
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.MvcResult
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import java.sql.Connection
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import javax.sql.DataSource
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** PostgreSQL lock barriers exercise the real SQL deadline and repeatable-read snapshot. */
class KnowledgeConcurrencyIntegrationTest : KnowledgePostgresTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var dataSource: DataSource
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper

    private val code = "4국02-04"
    private val originalStatement = "글에 나타난 사실과 의견을 구분하고 필자와 자신의 의견을 비교한다."

    private fun standards(): MvcResult = mvc.perform(
        get("/internal/knowledge/standards").param("codes", code).param("thinkingType", "EVALUATE")
            .header("X-Internal-Token", "knowledge-test-token").header("X-User-Role", "SYSTEM"),
    ).andReturn()

    private fun body(result: MvcResult): JsonNode = json.readTree(result.response.getContentAsString(Charsets.UTF_8))

    /** No arbitrary scheduling sleep: observe the exact relation lock wait with a bounded deadline. */
    private fun awaitChunkReader() {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(1500)
        do {
            val blocked = jdbc.queryForObject("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_locks
                    WHERE relation = 'public.knowledge_chunk'::regclass
                      AND mode = 'AccessShareLock' AND NOT granted
                )
            """.trimIndent(), Boolean::class.java) == true
            if (blocked) return
            Thread.sleep(10)
        } while (System.nanoTime() < deadline)
        error("Knowledge HTTP request did not reach the PostgreSQL chunk lock barrier")
    }

    private fun lockChunks(connection: Connection) {
        connection.autoCommit = false
        connection.createStatement().use {
            it.queryTimeout = 3
            it.execute("LOCK TABLE knowledge_chunk IN ACCESS EXCLUSIVE MODE")
        }
    }

    private fun stop(executor: ExecutorService, future: Future<*>?) {
        future?.cancel(true)
        executor.shutdownNow()
        assertTrue(executor.awaitTermination(5, TimeUnit.SECONDS), "HTTP test thread must terminate")
    }

    @Test fun `remaining SQL budget cancels a blocked query before the database lock is released`() {
        // Warm connection and mapping setup so the barrier measures SQL waiting rather than cold startup.
        assertEquals(200, standards().response.status)
        val executor = Executors.newSingleThreadExecutor()
        var future: Future<MvcResult>? = null
        try {
            dataSource.connection.use { locker ->
                lockChunks(locker)
                try {
                    val started = System.nanoTime()
                    val pending = executor.submit<MvcResult> { standards() }
                    future = pending
                    awaitChunkReader()
                    // The exclusive lock remains held here. Only cancellation can finish this request.
                    val response = pending.get(6, TimeUnit.SECONDS)
                    val elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started)
                    assertEquals(500, response.response.status)
                    assertEquals("INTERNAL_ERROR", body(response)["code"].asText())
                    assertTrue(elapsedMs < 6000, "The SQL request must not wait indefinitely: ${elapsedMs}ms")
                    val text = response.response.getContentAsString(Charsets.UTF_8)
                    assertFalse(text.contains("knowledge_chunk"))
                    assertFalse(text.contains("statement_timeout"))
                } finally {
                    locker.rollback()
                }
            }
            // Cancellation must roll back the read transaction and return a reusable connection.
            assertEquals(200, standards().response.status)
        } finally {
            stop(executor, future)
        }
    }

    @Test fun `an active dataset swap cannot mix versions or newer content into an in-flight bundle`() {
        val next = "kn-20261111-02"
        copyLoadingDataset(next)
        jdbc.update("UPDATE knowledge_chunk SET record=jsonb_set(record,'{statement}',?::jsonb) WHERE dataset_version=? AND id=?",
            json.writeValueAsString("새 판의 합성 문장"), next, code)
        assertEquals(200, standards().response.status)
        val executor = Executors.newSingleThreadExecutor()
        var future: Future<MvcResult>? = null
        try {
            dataSource.connection.use { locker ->
                lockChunks(locker)
                try {
                    val pending = executor.submit<MvcResult> { standards() }
                    future = pending
                    // findActiveDataset has read VERSION; the following findChunks is now blocked.
                    awaitChunkReader()
                    locker.prepareStatement("UPDATE knowledge_dataset SET status='RETIRED' WHERE version=?").use {
                        it.setString(1, VERSION)
                        assertEquals(1, it.executeUpdate())
                    }
                    locker.prepareStatement("UPDATE knowledge_dataset SET status='ACTIVE',activated_at=now() WHERE version=?").use {
                        it.setString(1, next)
                        assertEquals(1, it.executeUpdate())
                    }
                    // Reading old IDs alone is insufficient: snapshot isolation must also preserve their content.
                    locker.prepareStatement("UPDATE knowledge_chunk SET record=jsonb_set(record,'{statement}',?::jsonb) WHERE dataset_version=? AND id=?").use {
                        it.setString(1, json.writeValueAsString("스냅샷 이후 변경된 합성 문장"))
                        it.setString(2, VERSION)
                        it.setString(3, code)
                        assertEquals(1, it.executeUpdate())
                    }
                    locker.commit() // releases barrier only after both the activation and content change commit
                    val response = pending.get(5, TimeUnit.SECONDS)
                    assertEquals(200, response.response.status)
                    val oldBundle = body(response)
                    assertEquals(VERSION, oldBundle["datasetVersion"].asText())
                    assertEquals(originalStatement, oldBundle["items"].single()["standard"]["statement"].asText())
                    val oldRefs = references(oldBundle)
                    assertTrue(oldRefs.size >= 6, "Bundle must include standard/domain/covers/guide/type evidence")
                    assertTrue(oldRefs.all { it["datasetVersion"].asText() == VERSION })
                } finally {
                    locker.rollback()
                }
            }
            val response = standards()
            assertEquals(200, response.response.status)
            val newBundle = body(response)
            assertEquals(next, newBundle["datasetVersion"].asText())
            assertEquals("새 판의 합성 문장", newBundle["items"].single()["standard"]["statement"].asText())
            assertTrue(references(newBundle).all { it["datasetVersion"].asText() == next })
        } finally {
            stop(executor, future)
        }
    }

    private fun references(node: JsonNode): List<JsonNode> = buildList {
        if (node.isObject && node.has("kind") && node.has("id") && node.has("datasetVersion")) add(node)
        node.elements().forEachRemaining { if (it.isContainerNode) addAll(references(it)) }
    }

    private fun copyLoadingDataset(version: String) {
        jdbc.update("INSERT INTO knowledge_dataset SELECT ?, 'LOADING', source, embedding_model, embedding_dimensions, chunk_count, relation_count, created_at, NULL FROM knowledge_dataset WHERE version=?", version, VERSION)
        jdbc.update("""INSERT INTO knowledge_chunk SELECT ?,id,kind,subject,area,standard_code,domain_id,thinking_type,grades,semesters,notice_grade_band,
            text,record,embedding,content_hash,source FROM knowledge_chunk WHERE dataset_version=?""", version, VERSION)
        jdbc.update("INSERT INTO knowledge_standard_semester SELECT ?,standard_code,semester,grade FROM knowledge_standard_semester WHERE dataset_version=?", version, VERSION)
        jdbc.update("INSERT INTO knowledge_fits SELECT ?,standard_code,thinking_type,reason,reviewed_by,reviewed_at FROM knowledge_fits WHERE dataset_version=?", version, VERSION)
        jdbc.update("INSERT INTO knowledge_covers SELECT ?,standard_code,content_id,reviewed_by,reviewed_at FROM knowledge_covers WHERE dataset_version=?", version, VERSION)
        jdbc.update("INSERT INTO knowledge_prerequisite SELECT ?,standard_code,prerequisite_code,reason,reviewed_by,reviewed_at FROM knowledge_prerequisite WHERE dataset_version=?", version, VERSION)
    }
}
