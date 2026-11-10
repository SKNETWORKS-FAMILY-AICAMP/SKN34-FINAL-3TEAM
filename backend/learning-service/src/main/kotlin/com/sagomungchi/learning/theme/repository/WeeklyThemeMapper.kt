package com.sagomungchi.learning.theme.repository

import com.sagomungchi.learning.attempt.domain.AttemptContext
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** `weekly_theme` 행과 세 버전 번호(현재·게시·검토 요청) */
data class ThemeHeader(
    val id: UUID,
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val status: WeeklyThemeStatus,
    val currentVersionId: UUID,
    val currentVersion: Int,
    val publishedVersionId: UUID?,
    val publishedVersion: Int?,
    val reviewVersionId: UUID?,
    val reviewVersion: Int?,
    val createdBy: UUID,
    val publishedAt: Instant?,
    val createdAt: Instant,
    val updatedAt: Instant,
)

/** `weekly_theme_version`의 제목·소개 */
data class ThemeVersionRow(val id: UUID, val version: Int, val title: String, val intro: String)

/** 요일 미션과 그 미션의 표시용 제목·생각 유형(게시본, 없으면 현재본) */
data class ThemeDayRow(val dayOfWeek: Int, val missionId: UUID, val title: String, val thinkingType: ThinkingType)

/** 학생의 그 주 테마 시도 */
data class ThemeAttemptRow(
    val id: UUID,
    val missionId: UUID,
    val themeId: UUID,
    val context: AttemptContext,
    val status: AttemptStatus,
    val startedAt: Instant,
    val finishedAt: Instant?,
    val completedAt: Instant?,
)

@Mapper
interface WeeklyThemeMapper {
    fun findHeader(@Param("id") id: UUID, @Param("lock") lock: Boolean): ThemeHeader?
    fun findLatestPublished(@Param("grade") grade: ThemeGrade, @Param("weekStart") weekStart: LocalDate): ThemeHeader?
    fun existsOtherPublished(@Param("id") id: UUID, @Param("grade") grade: ThemeGrade, @Param("weekStart") weekStart: LocalDate): Boolean
    fun findIds(
        @Param("grade") grade: ThemeGrade?,
        @Param("weekStart") weekStart: LocalDate?,
        @Param("status") status: WeeklyThemeStatus?,
        @Param("size") size: Int,
        @Param("offset") offset: Long,
    ): List<UUID>
    fun count(
        @Param("grade") grade: ThemeGrade?,
        @Param("weekStart") weekStart: LocalDate?,
        @Param("status") status: WeeklyThemeStatus?,
    ): Long
    fun findVersion(versionId: UUID): ThemeVersionRow?
    fun findDays(versionId: UUID): List<ThemeDayRow>
    fun countMissions(@Param("ids") ids: List<UUID>): Int

    fun deferCurrentVersionCheck()
    fun insertTheme(
        @Param("id") id: UUID,
        @Param("grade") grade: ThemeGrade,
        @Param("weekStart") weekStart: LocalDate,
        @Param("status") status: WeeklyThemeStatus,
        @Param("versionId") versionId: UUID,
        @Param("createdBy") createdBy: UUID,
        @Param("now") now: Instant,
    ): Int
    fun insertVersion(
        @Param("id") id: UUID,
        @Param("themeId") themeId: UUID,
        @Param("version") version: Int,
        @Param("title") title: String,
        @Param("intro") intro: String,
        @Param("createdBy") createdBy: UUID,
        @Param("now") now: Instant,
    ): Int
    fun insertDay(@Param("versionId") versionId: UUID, @Param("dayOfWeek") dayOfWeek: Int, @Param("missionId") missionId: UUID): Int
    fun updateHeader(
        @Param("id") id: UUID,
        @Param("grade") grade: ThemeGrade,
        @Param("weekStart") weekStart: LocalDate,
        @Param("status") status: WeeklyThemeStatus,
        @Param("currentVersionId") currentVersionId: UUID,
        @Param("now") now: Instant,
    ): Int
    fun updateStatus(@Param("id") id: UUID, @Param("status") status: WeeklyThemeStatus, @Param("now") now: Instant): Int
    fun markReviewRequested(@Param("id") id: UUID, @Param("status") status: WeeklyThemeStatus, @Param("now") now: Instant): Int
    fun publish(@Param("id") id: UUID, @Param("now") now: Instant): Int

    fun findStudentAttempts(@Param("studentId") studentId: UUID, @Param("weekStart") weekStart: LocalDate): List<ThemeAttemptRow>
    fun insertReviewView(
        @Param("studentId") studentId: UUID,
        @Param("weekStart") weekStart: LocalDate,
        @Param("themeId") themeId: UUID,
        @Param("now") now: Instant,
    ): Int
    fun deleteReviewViewsByStudent(studentId: UUID): Int
}
