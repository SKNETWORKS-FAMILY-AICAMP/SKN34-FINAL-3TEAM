package com.sagomungchi.learning.knowledge.repository

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.learning.knowledge.dto.LearnedIn
import com.sagomungchi.learning.knowledge.dto.SearchFilters
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param

data class KnowledgeDatasetRow(val version: String, val embeddingModel: String, val embeddingDimensions: Int)
data class KnowledgeChunkRow(
    val id: String, val kind: String, val subject: String?, val area: String?, val standardCode: String?,
    val domainId: String?, val thinkingType: String?, val grades: JsonNode, val semesters: JsonNode,
    val noticeGradeBand: String?, val text: String, val record: JsonNode, val similarity: Double?,
)
data class KnowledgeCoverRow(val standardCode: String, val contentId: String)
data class KnowledgeFitRow(val standardCode: String, val thinkingType: String, val reason: String)
data class KnowledgeThemeRow(
    val thinkingType: String?, val code: String, val statement: String, val subject: String, val area: String,
    val similarity: Double, val matchedKind: String, val matchedId: String, val fitReason: String?,
)

@Mapper
interface KnowledgeQueryMapper {
    fun setLocalTimeout(@Param("milliseconds") milliseconds: String): String
    fun findActiveDataset(): KnowledgeDatasetRow?
    fun findChunks(@Param("version") version: String, @Param("kind") kind: String, @Param("ids") ids: List<String>): List<KnowledgeChunkRow>
    fun findSubjectGuides(@Param("version") version: String, @Param("subjects") subjects: List<String>): List<KnowledgeChunkRow>
    fun findCovers(@Param("version") version: String, @Param("codes") codes: List<String>): List<KnowledgeCoverRow>
    fun findFits(@Param("version") version: String, @Param("codes") codes: List<String>): List<KnowledgeFitRow>
    fun search(
        @Param("version") version: String, @Param("vector") vector: String, @Param("k") k: Int,
        @Param("minimum") minimum: Double, @Param("filters") filters: SearchFilters,
    ): List<KnowledgeChunkRow>
    fun themeCandidates(
        @Param("version") version: String, @Param("vector") vector: String, @Param("grade") grade: Int,
        @Param("semester") semester: String, @Param("k") k: Int, @Param("minimum") minimum: Double,
    ): List<KnowledgeThemeRow>
    fun nearestContent(@Param("version") version: String, @Param("vector") vector: String, @Param("minimum") minimum: Double): KnowledgeChunkRow?
    fun learnedIn(@Param("version") version: String, @Param("contentId") contentId: String): List<LearnedIn>
}
