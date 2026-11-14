package com.sagomungchi.learning.knowledge

import com.sagomungchi.learning.knowledge.controller.knowledgeObject

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.knowledge.domain.DatasetStatus
import com.sagomungchi.learning.knowledge.domain.KnowledgeInputException
import com.sagomungchi.learning.knowledge.domain.RelationType
import com.sagomungchi.learning.knowledge.repository.KnowledgeRepository
import com.sagomungchi.learning.knowledge.service.KnowledgeDatasetService
import com.sagomungchi.learning.knowledge.service.KnowledgeLoadCommand
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 지식 판 적재·재적재(멱등)·교체·제거·관계 옮기기 (#466, C9). 실제 PostgreSQL, 임베딩 없음(V17) */
@AutoConfigureMockMvc
class KnowledgeDatasetServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: KnowledgeDatasetService
    @Autowired lateinit var repository: KnowledgeRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper

    private val records = KnowledgeSamples.records
    private val source = KnowledgeSamples.dataset["source"]
    private val reviews = KnowledgeSamples.reviewedReviews
    private val accepted = reviews.filter { it.decision == "ACCEPT" || it.decision == "MODIFY" }
    private val semesterCount = records.filter { it["kind"].asText() == "standard" }.sumOf { it["semesters"].size() }

    @Test
    fun `샘플 적재는 LOADING 판에 215개 조각·학기 관계를 넣음`() {
        val result = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, emptyList()))
        val dataset = result.dataset
        assertTrue(Regex("^kn-\\d{8}-01$").matches(dataset.version))
        assertEquals(DatasetStatus.LOADING, dataset.status)
        assertEquals(215, dataset.chunkCount)
        assertEquals(mapOf("CONTENT" to 176, "DOMAIN" to 14, "STANDARD" to 15, "SUBJECT_GUIDE" to 5, "THINKING_TYPE" to 5), dataset.chunks)
        assertEquals(mapOf("SEMESTER" to semesterCount, "FITS" to 0, "PREREQUISITE" to 0, "COVERS" to 0), dataset.relations)
        assertEquals(semesterCount, dataset.relationCount)
        assertEquals(1, result.documents)
        assertNull(dataset.source["previousVersion"]?.takeUnless { it.isNull })
    }

    @Test
    fun `같은 입력을 다시 적재하면 같은 조각·관계 수, 교체 뒤 이전 판을 제거`() {
        val first = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, reviews))
        service.activate(first.dataset.version)
        val second = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, reviews))
        assertEquals(first.dataset.chunks, second.dataset.chunks)
        assertEquals(first.dataset.relations, second.dataset.relations)
        assertEquals(first.dataset.relationCount, second.dataset.relationCount)
        assertEquals(first.dataset.version, second.previousVersion)
        assertTrue(second.recheck.isEmpty())

        val activated = service.activate(second.dataset.version)
        assertEquals(DatasetStatus.ACTIVE, activated.status)
        assertEquals(DatasetStatus.RETIRED, service.get(first.dataset.version).status)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM knowledge_dataset WHERE status = 'ACTIVE'", Int::class.java))

        conflict { service.delete(second.dataset.version) } // ACTIVE는 지우지 않음
        service.delete(first.dataset.version)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM knowledge_chunk WHERE dataset_version = ?", Int::class.java, first.dataset.version))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM knowledge_covers WHERE dataset_version = ?", Int::class.java, first.dataset.version))
        assertNull(repository.findDataset(first.dataset.version))
        assertEquals(215, service.get(second.dataset.version).chunkCount)
    }

    @Test
    fun `확인 관계를 적재하고 covers로 내용 요소 학년·학기를 채움`() {
        val result = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, reviews))
        val byType = accepted.groupingBy { it.relationType!!.name }.eachCount()
        assertEquals(semesterCount, result.dataset.relations["SEMESTER"])
        assertEquals(byType["FITS"] ?: 0, result.dataset.relations["FITS"])
        assertEquals(byType["PREREQUISITE"] ?: 0, result.dataset.relations["PREREQUISITE"])
        assertEquals(byType["COVERS"] ?: 0, result.dataset.relations["COVERS"])
        val cover = accepted.first { it.relationType == RelationType.COVERS }
        val grades = jdbc.queryForObject(
            "SELECT array_to_string(grades, ',') FROM knowledge_chunk WHERE dataset_version = ? AND id = ?",
            String::class.java, result.dataset.version, if (cover.decision == "MODIFY") cover.modifiedTarget else cover.target,
        )!!
        assertTrue(grades.isNotEmpty())
    }

    @Test
    fun `끝이 없어진 관계는 옮기지 않고 다시 확인할 목록으로, 본문이 바뀐 끝은 옮기고 목록에도`() {
        val first = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, reviews))
        service.activate(first.dataset.version)
        val cover = accepted.first { it.relationType == RelationType.COVERS }
        val dropped = if (cover.decision == "MODIFY") cover.modifiedTarget else cover.target
        val fits = accepted.first { it.relationType == RelationType.FITS }
        val changed = records.filter { it["kind"].asText() != "content" || it["id"].asText() != dropped }.map { record ->
            if (record["kind"].asText() == "thinking_type" && record["type"].asText() == fits.target) {
                record.deepCopy<com.fasterxml.jackson.databind.node.ObjectNode>().put("name", record["name"].asText() + "(고침)")
            } else {
                record
            }
        }
        val coversOfDropped = accepted.count { it.relationType == RelationType.COVERS && (if (it.decision == "MODIFY") it.modifiedTarget else it.target) == dropped }
        val second = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), changed.map { knowledgeObject(it, "record") }, emptyList()))
        assertEquals(first.dataset.relations.getValue("COVERS") - coversOfDropped, second.dataset.relations["COVERS"])
        assertEquals(first.dataset.relations["FITS"], second.dataset.relations["FITS"])
        assertEquals(214, second.dataset.chunkCount)
        assertTrue(second.recheck.any { it.relationType == RelationType.COVERS && it.target == dropped && it.decision.isEmpty() })
        assertTrue(second.recheck.any { it.relationType == RelationType.FITS && it.target == fits.target })
    }

    @Test
    fun `활성 판이 적재 뒤 바뀌면 활성화 거부, LOADING·없는 판도 상태 오류`() {
        val a = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, emptyList()))
        val b = service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, emptyList()))
        service.activate(a.dataset.version)
        conflict { service.activate(b.dataset.version) }
        conflict { service.activate(a.dataset.version) }
        conflict { service.delete(b.dataset.version) } // LOADING도 지우지 않음
        val notFound = assertFailsWith<BusinessException> { service.get("kn-20000101-01") }
        assertEquals(HttpStatus.NOT_FOUND, notFound.status)
    }

    @Test
    fun `SAMPLE 확인 파일·성취기준 문장 불일치는 판을 만들기 전에 멈춤`() {
        assertFailsWith<KnowledgeInputException> { service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), records.map { knowledgeObject(it, "record") }, KnowledgeSamples.sampleReviews)) }
        val wrong = records.map {
            if (it["kind"].asText() == "standard" && it["code"].asText() == "4수01-06") {
                it.deepCopy<com.fasterxml.jackson.databind.node.ObjectNode>().put("statement", "고친 문장")
            } else {
                it
            }
        }
        val error = assertFailsWith<KnowledgeInputException> { service.load(KnowledgeLoadCommand(knowledgeObject(source, "source"), wrong.map { knowledgeObject(it, "record") }, emptyList())) }
        assertTrue(error.detail!!.contains("4수01-06"))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM knowledge_dataset", Int::class.java))
    }

    @Test
    fun `관리 API는 SYSTEM 역할만, 적재는 201`() {
        val body = json.writeValueAsString(mapOf("source" to source, "records" to records.take(20)))
        mvc.perform(get(PATH).header("X-Internal-Token", TOKEN).header("X-User-Role", "ADMIN")).andExpect(status().isForbidden)
        mvc.perform(post(PATH).header("X-Internal-Token", TOKEN).header("X-User-Role", "SYSTEM").contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isCreated)
            .andExpect(jsonPath("$.dataset.status").value("LOADING"))
            .andExpect(jsonPath("$.dataset.chunkCount").value(20))
        mvc.perform(post(PATH).header("X-Internal-Token", TOKEN).header("X-User-Role", "SYSTEM").contentType(MediaType.APPLICATION_JSON).content("{\"records\":[]}"))
            .andExpect(status().isBadRequest)
    }

    private fun conflict(block: () -> Unit) {
        val error = assertFailsWith<BusinessException> { block() }
        assertEquals(HttpStatus.CONFLICT, error.status)
    }

    private companion object {
        const val PATH = "/internal/admin/knowledge/datasets"
        const val TOKEN = "repository-test-token"
    }
}
