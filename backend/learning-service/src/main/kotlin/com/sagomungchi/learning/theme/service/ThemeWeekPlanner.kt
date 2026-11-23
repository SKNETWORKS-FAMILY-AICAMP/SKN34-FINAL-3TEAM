package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.repository.DraftWeekState
import com.sagomungchi.learning.theme.repository.PlannerDraft
import com.sagomungchi.learning.theme.repository.PlannerTheme
import com.sagomungchi.learning.theme.repository.ThemeWeekPlanMapper
import com.sagomungchi.learning.theme.repository.WeeklyThemeRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Isolation
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.UUID

data class WeekSlot(val weekStart: LocalDate, val locked: Boolean, val planned: PlannerDraft?, val themes: List<PlannerTheme>)
data class WeekBoard(val grade: ThemeGrade, val weekStart: LocalDate, val weeks: List<WeekSlot>, val candidates: List<PlannerDraft>)
data class PlanChange(val grade: ThemeGrade, val draftId: UUID, val expectedWeek: LocalDate?, val targetWeek: LocalDate?,
                      val expectedTargetDraftId: UUID?)
data class PlanResult(val draftId: UUID, val grade: ThemeGrade, val plannedWeek: LocalDate?, val displacedDraftId: UUID?)

@Service
class ThemeWeekPlanner(private val plans: ThemeWeekPlanMapper, private val themes: WeeklyThemeRepository, private val clock: Clock) {
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    fun board(grade: ThemeGrade, weekStart: LocalDate): WeekBoard {
        requireMonday(weekStart)
        val candidates = plans.candidates(grade)
        val byWeek = candidates.filter { it.plannedWeek != null }.associateBy { it.plannedWeek }
        val weeks = (0L..3L).map { offset ->
            val week = weekStart.plusWeeks(offset)
            val entries = plans.themes(grade, week)
            WeekSlot(week, entries.any { it.status == WeeklyThemeStatus.PUBLISHED }, byWeek[week], entries)
        }
        return WeekBoard(grade, weekStart, weeks, candidates)
    }

    @Transactional
    fun change(request: PlanChange): PlanResult {
        val (grade, id, from, to, expectedOther) = request
        from?.let(::requireMonday)
        to?.let {
            requireMonday(it)
            if (it.isBefore(ThemeWeek.startOf(LocalDate.now(clock)))) invalid("지나간 주에는 편성할 수 없습니다.")
        }
        lockGrades(grade)
        val state = state(id)
        if (state.grade != grade || state.status != DraftStatus.READY || !state.root || state.plannedWeek != from) {
            stale("초안 상태나 편성 주가 바뀌었습니다. 보드를 새로 확인해 주세요.")
        }
        if (from != null) requireOpen(grade, from)
        if (to != null) requireOpen(grade, to)
        val other = to?.let { plans.occupant(grade,it) }?.takeUnless { it == id }
        if (other != expectedOther) stale("대상 주의 편성 후보가 바뀌었습니다.")
        if (from == to) return PlanResult(id,grade,to,null)
        check(plans.assign(id,null) == 1)
        if (other != null) check(plans.assign(other,from) == 1)
        check(plans.assign(id,to) == 1)
        return PlanResult(id,grade,to,other)
    }

    fun state(id: UUID): DraftWeekState = plans.draftState(id)
        ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "테마 초안 없음")

    fun lockGrades(vararg grades: ThemeGrade) {
        grades.distinct().sortedBy { it.grade }.forEach { plans.lockGrade(it.grade) }
    }

    fun requireOpen(grade: ThemeGrade, week: LocalDate) {
        if (themes.existsPublished(grade,week)) locked()
    }

    fun generationWeek(themeId: UUID): LocalDate? = plans.generationWeek(themeId)

    @Transactional
    fun autoIfOpen(grade: ThemeGrade, week: LocalDate, generate: () -> Boolean): Boolean {
        lockGrades(grade)
        return !themes.existsPublished(grade,week) && generate()
    }

    fun lockDraftEdits(draftId: UUID): DraftWeekState {
        lockGrades(state(draftId).grade)
        val latest = state(draftId)
        if (latest.weekLocked) locked()
        return latest
    }

    fun requireExpected(state: DraftWeekState, expected: LocalDate?, supplied: Boolean) {
        if (supplied && state.plannedWeek != expected) stale("편성 주가 바뀌었습니다. 초안을 새로 확인해 주세요.")
    }

    fun clearDraft(id: UUID, state: DraftWeekState) {
        if (state.plannedWeek != null) check(plans.assign(id,null) == 1)
    }

    fun requireOccupant(grade: ThemeGrade, week: LocalDate, expected: UUID?) {
        if (plans.occupant(grade,week) != expected) stale("게시와 함께 해제할 편성 후보가 바뀌었습니다.")
    }

    fun lockMissions(versionId: UUID) { plans.lockMissions(versionId) }

    fun finishPublication(versionId: UUID, grade: ThemeGrade, week: LocalDate) {
        check(plans.freezeDays(versionId) == 5) { "게시할 요일 미션과 기준표 버전이 완전하지 않습니다." }
        plans.release(grade,week)
    }

    private fun requireMonday(date: LocalDate) {
        if (date.dayOfWeek != DayOfWeek.MONDAY) invalid("편성 주는 월요일 날짜여야 합니다.")
    }

    fun locked(): Nothing = throw BusinessException(HttpStatus.CONFLICT, "WEEK_LOCKED", "이미 게시가 확정된 주차입니다.")
    fun stale(detail: String): Nothing = throw BusinessException(HttpStatus.CONFLICT, "PLAN_CONFLICT", "편성 정보가 변경되었습니다.", detail)
    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "편성 날짜 오류", detail)
}
