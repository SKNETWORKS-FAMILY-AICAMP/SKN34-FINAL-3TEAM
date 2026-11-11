package com.sagomungchi.learning.knowledge.repository

import com.sagomungchi.learning.knowledge.domain.DatasetStatus
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant

/** `knowledge_dataset` 행. source는 JSON 글 */
data class DatasetRow(
    val version: String,
    val status: DatasetStatus,
    val source: String,
    val embeddingModel: String,
    val embeddingDimensions: Int,
    val chunkCount: Int,
    val relationCount: Int,
    val createdAt: Instant,
    val activatedAt: Instant?,
)

/** 넣을 조각. 배열·벡터·jsonb는 PostgreSQL 글 표기(`{3,4}`, `[0.1,…]`, JSON)로 넘겨 SQL에서 형변환 */
data class ChunkInsert(
    val datasetVersion: String,
    val id: String,
    val kind: String,
    val subject: String?,
    val area: String?,
    val standardCode: String?,
    val domainId: String?,
    val thinkingType: String?,
    val grades: String,
    val semesters: String,
    val noticeGradeBand: String?,
    val text: String,
    val record: String,
    val embedding: String,
    val contentHash: String,
    val source: String,
)

data class ChunkHashRow(val id: String, val kind: String, val contentHash: String)

data class HashEmbeddingRow(val contentHash: String, val embedding: String)

data class RelationRow(
    val type: String,
    val standardCode: String,
    val target: String,
    val reason: String?,
    val reviewedBy: String,
    val reviewedAt: Instant,
)

data class SemesterRow(val standardCode: String, val semester: String, val grade: Int)

data class StatementRow(val code: String, val statement: String)

data class KindCount(val kind: String, val count: Int)

@Mapper
interface KnowledgeMapper {
    fun findDataset(@Param("version") version: String, @Param("lock") lock: Boolean): DatasetRow?
    fun findDatasets(): List<DatasetRow>
    fun findActive(@Param("lock") lock: Boolean): DatasetRow?
    fun findVersionsWithPrefix(@Param("prefix") prefix: String): List<String>
    fun insertDataset(@Param("row") row: DatasetRow): Int
    fun updateCounts(@Param("version") version: String, @Param("chunkCount") chunkCount: Int, @Param("relationCount") relationCount: Int): Int
    fun updateStatus(
        @Param("version") version: String,
        @Param("status") status: DatasetStatus,
        @Param("activatedAt") activatedAt: Instant?,
    ): Int

    fun insertChunk(@Param("row") row: ChunkInsert): Int
    fun findChunkHashes(@Param("version") version: String): List<ChunkHashRow>
    fun findEmbeddingsByHash(@Param("version") version: String): List<HashEmbeddingRow>
    fun countMissingEmbeddings(@Param("version") version: String): Int
    fun countChunksByKind(@Param("version") version: String): List<KindCount>

    fun insertSemester(@Param("version") version: String, @Param("row") row: SemesterRow): Int
    fun insertRelation(@Param("version") version: String, @Param("row") row: RelationRow): Int
    fun findRelations(@Param("version") version: String): List<RelationRow>
    fun countRelations(@Param("version") version: String): List<KindCount>

    fun deleteVersionRows(@Param("table") table: String, @Param("column") column: String, @Param("version") version: String): Int

    fun findStatements(@Param("codes") codes: List<String>): List<StatementRow>
}
