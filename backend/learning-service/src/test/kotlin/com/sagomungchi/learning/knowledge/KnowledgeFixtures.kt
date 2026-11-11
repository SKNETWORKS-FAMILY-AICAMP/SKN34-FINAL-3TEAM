package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.knowledge.client.FakeKnowledgeEmbedder
import com.sagomungchi.learning.knowledge.domain.ChunkKind
import com.sagomungchi.learning.knowledge.domain.KnowledgeChunks
import com.sagomungchi.learning.knowledge.domain.KnowledgeRelations
import com.sagomungchi.learning.knowledge.domain.RelationReview
import com.sagomungchi.learning.knowledge.domain.RelationType
import org.springframework.jdbc.core.JdbcTemplate

/** Public #524 samples in the real V14 schema. Every review marker here is synthetic test data. */
internal class KnowledgeFixtures(private val jdbc: JdbcTemplate, private val json: ObjectMapper) {
    companion object {
        const val VERSION = "kn-20261111-01"
        const val MODEL = FakeKnowledgeEmbedder.MODEL
        const val DIMENSIONS = 1536
        const val DIVISION = "수학:초3~4:수와 연산:K:cfcd0e59"
        const val MULTIPLICATION = "수학:초3~4:수와 연산:K:763df0ce"
        const val UNREVIEWED = "국어:초3~4:듣기⋅말하기:P:ef484719"
        val TYPES = listOf("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT")

        fun axis(index: Int = 0): List<Double> = List(DIMENSIONS) { if (it == index) 1.0 else 0.0 }
        fun vectorSql(vector: List<Double>) = vector.joinToString(",", "[", "]")
        fun vector(text: String): List<Double> = FakeKnowledgeEmbedder().vector(text).map(Float::toDouble)

        /** Unchanged sample CSV; TEST_FIXTURE permits isolated tests and is never a human approval. */
        fun syntheticReviews(): List<RelationReview> = KnowledgeSamples.sampleReviews.map {
            if (it.decision.isEmpty()) it else it.copy(reviewer = "TEST_FIXTURE")
        }
    }

    fun load() {
        val metadata = KnowledgeSamples.dataset
        check(metadata["version"].asText() == VERSION && metadata["sample"].asBoolean())
        val relations = KnowledgeRelations.decide(emptyList(), syntheticReviews())
        val chunks = KnowledgeChunks.withCovers(
            KnowledgeChunks.fromRecords(KnowledgeSamples.records),
            relations.filter { it.type == RelationType.COVERS }.map { it.standardCode to it.target },
        )
        val standards = chunks.filter { it.kind == ChunkKind.STANDARD }
        val relationCount = relations.size + standards.sumOf { it.semesters.size }
        jdbc.update("""
            INSERT INTO knowledge_dataset
                (version,status,source,embedding_model,embedding_dimensions,chunk_count,relation_count,created_at,activated_at)
            VALUES (?, 'ACTIVE', ?::jsonb, ?, ?, ?, ?, now(), now())
        """.trimIndent(), VERSION, json.writeValueAsString(metadata["source"]), MODEL, DIMENSIONS, chunks.size, relationCount)
        chunks.forEach { chunk ->
            jdbc.update("""
                INSERT INTO knowledge_chunk (dataset_version,id,kind,subject,area,standard_code,domain_id,
                    thinking_type,grades,semesters,notice_grade_band,text,record,embedding,content_hash,source)
                VALUES (?,?,?,?,?,?,?,?,?::smallint[],?::varchar[],?,?,?::jsonb,?::vector,?,?::jsonb)
            """.trimIndent(), VERSION, chunk.id, chunk.kind.name, chunk.subject, chunk.area, chunk.standardCode,
                chunk.domainId, chunk.thinkingType, chunk.grades.joinToString(",", "{", "}"),
                chunk.semesters.joinToString(",", "{", "}"), chunk.noticeGradeBand, chunk.text,
                json.writeValueAsString(chunk.record), vectorSql(vector(chunk.text)), chunk.contentHash,
                json.writeValueAsString(chunk.source))
        }
        standards.forEach { standard -> standard.semesters.forEach { semester ->
            jdbc.update("INSERT INTO knowledge_standard_semester VALUES (?,?,?,?)",
                VERSION, standard.id, semester, KnowledgeChunks.gradeOfSemester(semester))
        } }
        relations.forEach { relation ->
            when (relation.type) {
                RelationType.FITS -> jdbc.update("INSERT INTO knowledge_fits VALUES (?,?,?,?,?,?::timestamptz)",
                    VERSION, relation.standardCode, relation.target, relation.reason, relation.reviewedBy, relation.reviewedAt.toString())
                RelationType.COVERS -> jdbc.update("INSERT INTO knowledge_covers VALUES (?,?,?,?,?::timestamptz)",
                    VERSION, relation.standardCode, relation.target, relation.reviewedBy, relation.reviewedAt.toString())
                RelationType.PREREQUISITE -> jdbc.update("INSERT INTO knowledge_prerequisite VALUES (?,?,?,?,?,?::timestamptz)",
                    VERSION, relation.standardCode, relation.target, relation.reason, relation.reviewedBy, relation.reviewedAt.toString())
            }
        }
    }
}
