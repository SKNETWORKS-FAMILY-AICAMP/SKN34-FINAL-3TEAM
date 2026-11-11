package com.sagomungchi.learning.knowledge.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.knowledge.domain.DatasetStatus
import com.sagomungchi.learning.knowledge.domain.KnowledgeChunk
import com.sagomungchi.learning.knowledge.domain.KnowledgeRelation
import com.sagomungchi.learning.knowledge.domain.RelationType
import org.springframework.stereotype.Repository
import java.time.Instant

/** 지식 판·조각·관계(erd 4.5). 트랜잭션은 시작하지 않음 */
@Repository
class KnowledgeRepository(
    private val mapper: KnowledgeMapper,
    private val objectMapper: ObjectMapper,
) {
    fun findDataset(version: String, lock: Boolean = false): DatasetRow? = mapper.findDataset(version, lock)

    fun findDatasets(): List<DatasetRow> = mapper.findDatasets()

    fun findActive(lock: Boolean = false): DatasetRow? = mapper.findActive(lock)

    fun findVersionsWithPrefix(prefix: String): List<String> = mapper.findVersionsWithPrefix(prefix)

    fun insertDataset(row: DatasetRow) = check(mapper.insertDataset(row) == 1)

    fun updateCounts(version: String, chunkCount: Int, relationCount: Int) = check(mapper.updateCounts(version, chunkCount, relationCount) == 1)

    fun updateStatus(version: String, status: DatasetStatus, activatedAt: Instant? = null) =
        check(mapper.updateStatus(version, status, activatedAt) == 1)

    fun insertChunk(version: String, chunk: KnowledgeChunk, embedding: FloatArray) {
        val row = ChunkInsert(
            datasetVersion = version,
            id = chunk.id,
            kind = chunk.kind.name,
            subject = chunk.subject,
            area = chunk.area,
            standardCode = chunk.standardCode,
            domainId = chunk.domainId,
            thinkingType = chunk.thinkingType,
            grades = chunk.grades.joinToString(",", "{", "}"),
            semesters = chunk.semesters.joinToString(",", "{", "}"),
            noticeGradeBand = chunk.noticeGradeBand,
            text = chunk.text,
            record = objectMapper.writeValueAsString(chunk.record),
            embedding = vectorText(embedding),
            contentHash = chunk.contentHash,
            source = objectMapper.writeValueAsString(chunk.source),
        )
        check(mapper.insertChunk(row) == 1)
    }

    /** 조각 ID → (종류, 본문 해시) */
    fun findChunkHashes(version: String): Map<String, ChunkHashRow> = mapper.findChunkHashes(version).associateBy { it.id }

    /** 본문 해시 → 벡터(같은 본문 임베딩 재사용) */
    fun findEmbeddingsByHash(version: String): Map<String, FloatArray> =
        mapper.findEmbeddingsByHash(version).associate { it.contentHash to parseVector(it.embedding) }

    fun countMissingEmbeddings(version: String): Int = mapper.countMissingEmbeddings(version)

    fun countChunksByKind(version: String): Map<String, Int> = mapper.countChunksByKind(version).associate { it.kind to it.count }

    fun insertSemester(version: String, standardCode: String, semester: String, grade: Int) =
        check(mapper.insertSemester(version, SemesterRow(standardCode, semester, grade)) == 1)

    fun insertRelation(version: String, relation: KnowledgeRelation) {
        val row = RelationRow(
            relation.type.name, relation.standardCode, relation.target, relation.reason, relation.reviewedBy, relation.reviewedAt,
        )
        check(mapper.insertRelation(version, row) == 1)
    }

    fun findRelations(version: String): List<KnowledgeRelation> = mapper.findRelations(version).map {
        KnowledgeRelation(RelationType.valueOf(it.type), it.standardCode, it.target, it.reason.orEmpty(), it.reviewedBy, it.reviewedAt)
    }

    /** SEMESTER·FITS·PREREQUISITE·COVERS 행 수 */
    fun countRelations(version: String): Map<String, Int> = mapper.countRelations(version).associate { it.kind to it.count }

    /** 제거(C9): 관계 → 조각 → 판 순서. 호출하는 쪽이 한 트랜잭션으로 묶음 */
    fun deleteDataset(version: String) {
        for ((table, column) in DELETE_ORDER) mapper.deleteVersionRows(table, column, version)
    }

    /** 성취기준 코드 → 문장(achievement_standard) */
    fun findStatements(codes: Collection<String>): Map<String, String> =
        if (codes.isEmpty()) emptyMap() else codes.distinct().chunked(500).flatMap { mapper.findStatements(it) }.associate { it.code to it.statement }

    companion object {
        private val DELETE_ORDER = listOf(
            "knowledge_standard_semester" to "dataset_version",
            "knowledge_fits" to "dataset_version",
            "knowledge_prerequisite" to "dataset_version",
            "knowledge_covers" to "dataset_version",
            "knowledge_chunk" to "dataset_version",
            "knowledge_dataset" to "version",
        )

        /** pgvector 글 표기 `[0.1,0.2,…]` (Float.toString은 지수 표기도 pgvector가 읽음) */
        fun vectorText(values: FloatArray): String = values.joinToString(",", "[", "]")

        fun parseVector(text: String): FloatArray =
            text.trim().removePrefix("[").removeSuffix("]").split(',').map { it.trim().toFloat() }.toFloatArray()
    }
}
