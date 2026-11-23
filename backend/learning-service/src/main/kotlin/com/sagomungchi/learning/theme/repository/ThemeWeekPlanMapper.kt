package com.sagomungchi.learning.theme.repository

import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.LocalDate
import java.util.UUID

data class PlannerDraft(val draftId: UUID, val title: String, val generationWeek: LocalDate, val plannedWeek: LocalDate?)
data class PlannerTheme(val themeId: UUID, val title: String, val status: WeeklyThemeStatus, val version: Int)
data class DraftWeekState(val grade: ThemeGrade, val status: DraftStatus, val generationWeek: LocalDate, val plannedWeek: LocalDate?,
                          val weekLocked: Boolean, val adoptionWeekLocked: Boolean, val root: Boolean)

@Mapper
interface ThemeWeekPlanMapper {
    fun lockGrade(@Param("grade") grade: Int): Int
    fun draftState(id: UUID): DraftWeekState?
    fun generationWeek(themeId: UUID): LocalDate?
    fun candidates(grade: ThemeGrade): List<PlannerDraft>
    fun themes(@Param("grade") grade: ThemeGrade, @Param("week") week: LocalDate): List<PlannerTheme>
    fun occupant(@Param("grade") grade: ThemeGrade, @Param("week") week: LocalDate): UUID?
    fun assign(@Param("id") id: UUID, @Param("week") week: LocalDate?): Int
    fun release(@Param("grade") grade: ThemeGrade, @Param("week") week: LocalDate): Int
    fun lockMissions(versionId: UUID): List<UUID>
    fun freezeDays(versionId: UUID): Int
}
