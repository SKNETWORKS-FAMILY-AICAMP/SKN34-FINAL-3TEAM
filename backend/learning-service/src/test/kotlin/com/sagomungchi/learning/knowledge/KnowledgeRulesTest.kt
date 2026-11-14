package com.sagomungchi.learning.knowledge

import com.sagomungchi.learning.knowledge.controller.knowledgeObject

import com.sagomungchi.learning.knowledge.domain.ChunkKind
import com.sagomungchi.learning.knowledge.domain.KnowledgeChunks
import com.sagomungchi.learning.knowledge.domain.KnowledgeInputException
import com.sagomungchi.learning.knowledge.domain.KnowledgeRelation
import com.sagomungchi.learning.knowledge.domain.KnowledgeRelations
import com.sagomungchi.learning.knowledge.domain.RelationReview
import com.sagomungchi.learning.knowledge.domain.RelationType
import org.junit.jupiter.api.Test
import java.time.Instant
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/** 조각 규칙이 ai 가짜 구현(fake.py)과 같은지, C4 → C3 규칙 (#466, erd 4.5) */
class KnowledgeRulesTest {
    private val chunks = KnowledgeChunks.fromRecords(KnowledgeSamples.records.map { knowledgeObject(it, "record") })

    @Test
    fun `객체가 아닌 입력도 기존 오류 내용을 유지한다`() {
        val scalar = com.fasterxml.jackson.databind.ObjectMapper().readTree("3")
        assertEquals("source는 객체", assertFailsWith<KnowledgeInputException> {
            knowledgeObject(scalar, "source")
        }.detail)
        assertEquals("records[0]: kind 필요", assertFailsWith<KnowledgeInputException> {
            knowledgeObject(scalar, "records[0]")
        }.detail)
    }

    @Test
    fun `실제 1341개 레코드의 본문 해시와 JSON 값이 변하지 않는다`() {
        val mapper = com.fasterxml.jackson.databind.ObjectMapper()
        val nodes = java.io.File("../../scripts/knowledge/data/curriculum-v1.jsonl")
            .readLines(Charsets.UTF_8).filter { it.isNotBlank() }.map { mapper.readTree(it) }
        val actual = KnowledgeChunks.fromRecords(nodes.map { knowledgeObject(it, "record") })
        assertEquals(1341, actual.size)
        // 기존 ai fake.chunk_text/content_hash로 산출한 순서별 해시 묶음. 구현 결과로 재생성하지 않는다.
        assertEquals("c451f0aaff2cea7257c77d138e8df2cda5519c629b1b604ea7568090b84ff002",
            KnowledgeChunks.sha256(actual.joinToString("\n") { it.contentHash }))
        actual.zip(nodes).forEach { (chunk, original) ->
            assertEquals(original, mapper.readTree(mapper.writeValueAsString(chunk.record)), chunk.id)
            assertEquals(original["source"], mapper.readTree(mapper.writeValueAsString(chunk.source)), chunk.id)
        }
    }

    @Test
    fun `샘플 215개 조각의 본문 해시가 fake·chunk_text와 같음`() {
        val expected = KnowledgeSamples.parity["contentHashes"]
        assertEquals(215, chunks.size)
        assertEquals(mapOf(ChunkKind.STANDARD to 15, ChunkKind.DOMAIN to 14, ChunkKind.CONTENT to 176,
            ChunkKind.SUBJECT_GUIDE to 5, ChunkKind.THINKING_TYPE to 5), chunks.groupingBy { it.kind }.eachCount())
        chunks.forEach { assertEquals(expected[it.id].asText(), it.contentHash, it.id) }
    }

    @Test
    fun `확인된 covers로 내용 요소·영역 학년·학기를 fake와 같게 채움`() {
        // fake는 샘플 파일(SAMPLE 포함)을 그대로 쓰므로 같은 ACCEPT·MODIFY covers로 대조
        val covers = KnowledgeSamples.reviewedReviews.filter { it.relationType == RelationType.COVERS && it.decision in setOf("ACCEPT", "MODIFY") }
            .map { it.standardCode to (if (it.decision == "MODIFY") it.modifiedTarget else it.target) }
        val filled = KnowledgeChunks.withCovers(chunks, covers)
        val grades = KnowledgeSamples.parity["grades"]
        val semesters = KnowledgeSamples.parity["semesters"]
        filled.filter { it.kind == ChunkKind.CONTENT || it.kind == ChunkKind.DOMAIN }.forEach { chunk ->
            assertEquals(grades[chunk.id].map { it.asInt() }, chunk.grades, chunk.id)
            assertEquals(semesters[chunk.id].map { it.asText() }, chunk.semesters, chunk.id)
        }
        assertTrue(filled.any { it.kind == ChunkKind.CONTENT && it.semesters.isNotEmpty() })
    }

    @Test
    fun `같은 판 안에서 조각 ID가 겹치면 멈춤`() {
        assertFailsWith<KnowledgeInputException> { KnowledgeChunks.fromRecords((KnowledgeSamples.records + KnowledgeSamples.records.first()).map { knowledgeObject(it, "record") }) }
    }

    @Test
    fun `SAMPLE 확인 행은 거부`() {
        val error = assertFailsWith<KnowledgeInputException> { KnowledgeRelations.decide(emptyList(), KnowledgeSamples.sampleReviews) }
        assertTrue(error.detail!!.contains("SAMPLE"))
    }

    @Test
    fun `MODIFY는 바꾼 대상, 늦은 확인이 이기고 늦은 REJECT는 옮긴 관계를 뺌, 확인 전 행은 무시`() {
        val carried = listOf(
            KnowledgeRelation(RelationType.FITS, "4수01-06", "SOLVE", "옛 근거", "갑", Instant.parse("2026-11-01T00:00:00Z")),
            KnowledgeRelation(RelationType.FITS, "4수01-06", "ANALYZE", "옛 근거", "갑", Instant.parse("2026-11-01T00:00:00Z")),
        )
        val reviews = listOf(
            review("4수01-06", "SOLVE", "REJECT", reason = "유형 아님", at = "2026-11-10"),
            review("4수01-06", "ANALYZE", "ACCEPT", reason = "새 근거", at = "2026-10-01"),
            review("4수01-06", "CREATE", "MODIFY", modified = "REFLECT", reason = "돌아보기", at = "2026-11-10"),
            review("4수01-06", "EVALUATE", ""),
        )
        val result = KnowledgeRelations.decide(carried, reviews).associateBy { it.target }
        assertEquals(setOf("ANALYZE", "REFLECT"), result.keys)
        assertEquals("옛 근거", result.getValue("ANALYZE").reason)
        assertEquals(Instant.parse("2026-11-09T15:00:00Z"), result.getValue("REFLECT").reviewedAt)
    }

    @Test
    fun `REJECT·MODIFY는 reason 필요`() {
        assertFailsWith<KnowledgeInputException> {
            KnowledgeRelations.decide(emptyList(), listOf(review("4수01-06", "SOLVE", "REJECT", at = "2026-11-10")))
        }
    }

    private fun review(code: String, target: String, decision: String, modified: String = "", reason: String = "", at: String = "") =
        RelationReview(
            relationType = RelationType.FITS, standardCode = code, target = target, decision = decision, modifiedTarget = modified,
            reason = reason, reviewer = if (decision.isEmpty()) "" else "검토자", reviewedAt = at,
        )
}
