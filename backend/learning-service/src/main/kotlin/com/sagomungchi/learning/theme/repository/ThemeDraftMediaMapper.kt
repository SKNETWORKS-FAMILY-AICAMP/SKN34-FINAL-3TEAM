package com.sagomungchi.learning.theme.repository

import com.sagomungchi.learning.mission.domain.DraftStatus
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

data class SceneSourceRow(val id: UUID, val status: DraftStatus, val createdAt: Instant,
    val image: String?, val video: String?, val motion: Map<String, Any?>?, val starred: Boolean, val note: String, val unreviewed: Boolean)

data class SceneChoiceRow(val scene: String, val versionId: UUID)

@Mapper
interface ThemeDraftMediaMapper {
    fun rootId(@Param("id") id: UUID): UUID?
    fun hasGenerating(@Param("root") root: UUID): Boolean
    fun hasAdopted(@Param("root") root: UUID): Boolean
    fun sources(@Param("root") root: UUID, @Param("scene") scene: String): List<SceneSourceRow>
    fun ancestors(@Param("id") id: UUID): List<UUID>
    fun choices(@Param("id") id: UUID): List<SceneChoiceRow>
    fun freeze(@Param("id") id: UUID)
    fun select(@Param("root") root: UUID, @Param("scene") scene: String, @Param("version") version: UUID,
        @Param("reviewed") reviewed: List<UUID>)
    fun annotate(@Param("scene") scene: String, @Param("version") version: UUID, @Param("starred") starred: Boolean?, @Param("note") note: String?)
}
