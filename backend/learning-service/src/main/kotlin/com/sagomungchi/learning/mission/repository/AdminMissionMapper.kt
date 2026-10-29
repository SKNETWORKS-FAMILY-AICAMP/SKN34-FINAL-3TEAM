package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.mission.domain.AdminMissionFilter
import com.sagomungchi.learning.mission.domain.AdminMissionVersion
import com.sagomungchi.learning.mission.domain.AdminReview
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.ReviewResult
import com.sagomungchi.learning.mission.domain.StatusCount
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

/** 관리자 미션 SQL (#145). MissionRepository가 학생 조회용 MissionMapper와 함께 씀 */
@Mapper
interface AdminMissionMapper {
    fun lockMission(id: UUID): UUID?
    fun findMissionHeader(id: UUID): MissionHeader?
    fun findMissionIds(@Param("filter") filter: AdminMissionFilter, @Param("offset") offset: Long): List<UUID>
    fun countMissions(@Param("filter") filter: AdminMissionFilter): Long
    fun countByStatus(): List<StatusCount>
    fun findAdminVersions(missionId: UUID): List<AdminMissionVersion>
    fun findReviews(missionId: UUID): List<AdminReview>
    fun nextSortOrder(): Int
    fun nextVersion(missionId: UUID): Int
    fun insertMission(
        @Param("id") id: UUID,
        @Param("code") code: String,
        @Param("demoOnly") demoOnly: Boolean,
        @Param("sortOrder") sortOrder: Int,
        @Param("authorId") authorId: UUID,
        @Param("now") now: Instant,
    ): Int
    fun insertVersion(
        @Param("id") id: UUID,
        @Param("missionId") missionId: UUID,
        @Param("version") version: Int,
        @Param("command") command: MissionCommand,
        @Param("now") now: Instant,
    ): Int
    fun updateCurrentVersion(
        @Param("missionId") missionId: UUID,
        @Param("versionId") versionId: UUID,
        @Param("demoOnly") demoOnly: Boolean,
        @Param("now") now: Instant,
    ): Int
    fun updateStatus(@Param("missionId") missionId: UUID, @Param("status") status: MissionStatus, @Param("now") now: Instant): Int
    fun publish(@Param("missionId") missionId: UUID, @Param("now") now: Instant): Int
    fun insertReview(
        @Param("id") id: UUID,
        @Param("missionId") missionId: UUID,
        @Param("reviewerId") reviewerId: UUID,
        @Param("result") result: ReviewResult,
        @Param("comment") comment: String?,
        @Param("now") now: Instant,
    ): Int
}
/**
 * 관리자용 미션 행. 버전은 번호(편집 중 current*, 학생 제공 published*), currentVersionId는 미리보기·검토 행 저장용
 */
data class MissionHeader(
    val id: UUID,
    val code: String,
    val status: MissionStatus,
    val demoOnly: Boolean,
    val currentVersionId: UUID,
    val currentVersion: Int,
    val currentRubricVersion: Int?,
    val publishedVersion: Int?,
    val publishedRubricVersion: Int?,
)
