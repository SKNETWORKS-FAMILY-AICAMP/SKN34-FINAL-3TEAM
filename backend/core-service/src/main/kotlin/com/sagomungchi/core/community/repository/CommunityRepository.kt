package com.sagomungchi.core.community.repository

import com.sagomungchi.core.community.domain.CommunityAuthor
import com.sagomungchi.core.community.domain.CommunityReportState
import com.sagomungchi.core.community.domain.CommunityState
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface CommunityMapper {
    fun state(@Param("studentId") studentId: UUID, @Param("lock") lock: Boolean): CommunityState?
    fun update(@Param("studentId") studentId: UUID, @Param("enabled") enabled: Boolean, @Param("now") now: OffsetDateTime): Int
    fun disable(@Param("studentId") studentId: UUID, @Param("now") now: OffsetDateTime): Int
    fun reset(@Param("studentId") studentId: UUID): Int
    fun authors(@Param("ids") ids: Collection<UUID>): List<CommunityAuthor>
    fun reportHidden(@Param("ids") ids: Collection<UUID>): List<UUID>
    fun reports(@Param("postId") postId: UUID): List<CommunityReportState>
}

@Repository
class CommunityRepository(private val mapper: CommunityMapper) {
    fun state(studentId: UUID, lock: Boolean = false) = mapper.state(studentId, lock)
    fun update(studentId: UUID, enabled: Boolean, now: OffsetDateTime) = mapper.update(studentId, enabled, now)
    fun disable(studentId: UUID, now: OffsetDateTime) = mapper.disable(studentId, now)
    fun reset(studentId: UUID) { mapper.reset(studentId) }
    fun authors(ids: Collection<UUID>) = if (ids.isEmpty()) emptyList() else mapper.authors(ids)
    fun reportHidden(ids: Collection<UUID>): Set<UUID> = if (ids.isEmpty()) emptySet() else mapper.reportHidden(ids).toSet()
    fun reports(postId: UUID) = mapper.reports(postId)
}
