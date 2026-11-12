package com.sagomungchi.learning.knowledge.repository

import com.fasterxml.jackson.databind.JsonNode
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param

data class KnowledgeDatasetRow(val version: String)
data class KnowledgeChunkRow(
    val id: String, val kind: String, val subject: String?, val area: String?, val standardCode: String?,
    val domainId: String?, val thinkingType: String?, val grades: JsonNode, val semesters: JsonNode,
    val noticeGradeBand: String?, val text: String, val record: JsonNode,
)
data class KnowledgeCoverRow(val standardCode: String, val contentId: String)
data class KnowledgeFitRow(val standardCode: String, val thinkingType: String, val reason: String)
@Mapper
interface KnowledgeQueryMapper {
    fun setLocalTimeout(@Param("milliseconds") milliseconds: String): String
    fun findActiveDataset(): KnowledgeDatasetRow?
    fun findChunks(@Param("version") version: String, @Param("kind") kind: String, @Param("ids") ids: List<String>): List<KnowledgeChunkRow>
    fun findSubjectGuides(@Param("version") version: String, @Param("subjects") subjects: List<String>): List<KnowledgeChunkRow>
    fun findCovers(@Param("version") version: String, @Param("codes") codes: List<String>): List<KnowledgeCoverRow>
    fun findFits(@Param("version") version: String, @Param("codes") codes: List<String>): List<KnowledgeFitRow>
}
