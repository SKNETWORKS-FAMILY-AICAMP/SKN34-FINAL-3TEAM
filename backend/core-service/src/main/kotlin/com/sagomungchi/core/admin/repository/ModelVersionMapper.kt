package com.sagomungchi.core.admin.repository

import com.fasterxml.jackson.databind.JsonNode
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import java.util.UUID

/** Persistence representation only: JSON conversion stays inside this package. */
data class ModelVersionRow(val id: UUID, val kind: String, val name: String, val version: String,
    val refId: UUID?, val artifactUri: String?, val evalResult: JsonNode?, val status: String,
    val approvedBy: UUID?, val activatedAt: OffsetDateTime?, val createdAt: OffsetDateTime)

@Mapper
interface ModelVersionMapper {
    fun insert(row: ModelVersionRow): Int
    fun find(id: UUID): ModelVersionRow?
    fun list(@Param("kind") kind: String?, @Param("offset") offset: Long, @Param("size") size: Int): List<ModelVersionRow>
    fun count(kind: String?): Long
    fun active(): List<ModelVersionRow>
    fun current(@Param("kind") kind: String, @Param("name") name: String): ModelVersionRow?
    fun lockGroup(@Param("kind") kind: String, @Param("name") name: String): String
    fun nextRevision(@Param("kind") kind: String, @Param("name") name: String): Long
    fun update(row: ModelVersionRow): Int
    fun audit(@Param("id") id: UUID, @Param("actor") actor: UUID, @Param("action") action: String,
              @Param("target") target: UUID, @Param("detail") detail: JsonNode, @Param("now") now: OffsetDateTime): Int
}
