package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.attempt.domain.AttemptContext
import com.sagomungchi.learning.attempt.domain.ThemeAttempt
import com.sagomungchi.learning.theme.domain.DayState
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeSummaryState
import com.sagomungchi.learning.theme.repository.WeeklyThemeRepository
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Clock
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 학생 주간 테마 (#385, P23): 요일 상태·재사용·시작 검사·되돌아보기 열람·완주·주간 요약 */
class WeeklyThemeServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var repository: WeeklyThemeRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var reports: WeeklyThemeReportService

    private lateinit var rows: TestRows
    private lateinit var missions: List<TestRows.SeededMission>
    private lateinit var themeId: UUID
    private val student = UUID.randomUUID()

    @BeforeEach
    fun seed() {
        rows = TestRows(jdbc)
        missions = rows.themeMissions()
        themeId = rows.publishedTheme(missions.map { it.id }, WEEK, title = "물의 여행", intro = "이번 주는 물")
    }

    @Test
    fun `학생은 자기 학년 테마를 받고 중학생은 G6 테마 (#438)`() {
        // 같은 미션으로 학년마다 다른 제목의 테마를 게시. 기본 테마(G3) 미션은 3~4학년이라 G4에도 맞음
        val wide = rows.themeMissions(gradeMin = 3, gradeMax = 6)
        val byGrade = listOf(ThemeGrade.G4, ThemeGrade.G5, ThemeGrade.G6).associateWith { grade ->
            rows.publishedTheme(wide.map { it.id }, WEEK, grade = grade.name, title = "${grade.name} 테마")
        }
        val service = serviceOn(WEEK)

        assertEquals("물의 여행", service.current(student, ThemeGrade.G3, WEEK).title)
        byGrade.forEach { (grade, id) ->
            assertEquals(id, service.current(student, grade, WEEK).themeId)
            assertEquals("${grade.name} 테마", service.current(student, grade, WEEK).title)
        }
        // 시도 시작은 시도 학년으로 테마를 정함: 4학년은 G4, 중학생(7~9)은 G6
        assertEquals(ThemeAttempt(byGrade.getValue(ThemeGrade.G4), WEEK), service.checkStart(student, wide[0].id, 4, AttemptContext.THEME_DAY))
        assertEquals(ThemeAttempt(byGrade.getValue(ThemeGrade.G6), WEEK), service.checkStart(student, wide[0].id, 8, AttemptContext.THEME_DAY))
        // 3학년 테마의 미션은 4학년 테마에 없으니 4학년 시작은 409
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { service.checkStart(student, missions[0].id, 4, AttemptContext.THEME_DAY) }
    }

    /** 그 날짜 KST 정오의 고정 시계 */
    private fun serviceOn(date: LocalDate) =
        WeeklyThemeService(repository, Clock.fixed(date.atTime(12, 0).atZone(KST).toInstant(), KST))

    private fun at(date: LocalDate, hour: Int = 10): OffsetDateTime = date.atTime(hour, 0).atZone(KST).toOffsetDateTime()

    /** 테마 시도 행 직접 삽입 (시각을 정하려고) */
    private fun attempt(
        mission: TestRows.SeededMission,
        context: String,
        startedAt: OffsetDateTime,
        finishedAt: OffsetDateTime? = null,
        completedAt: OffsetDateTime? = null,
        theme: UUID = themeId,
        week: LocalDate = WEEK,
        studentId: UUID = student,
    ): UUID = UUID.randomUUID().also {
        jdbc.update(
            """INSERT INTO attempt (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status,
                   started_at, finished_at, completed_at, updated_at, context, theme_id, theme_week_start)
               VALUES (?, ?, ?, ?, ?, 3, ?, ?, ?, ?, ?, ?, ?, ?)""",
            it, studentId, mission.id, mission.versionId, mission.rubricVersionId, if (completedAt != null) "COMPLETED" else "IN_PROGRESS",
            startedAt, finishedAt, completedAt, startedAt, context, theme, week,
        )
    }

    @Test
    fun `리포트 요약은 미마무리 다시 풀기의 비교를 공개하지 않음`() {
        attempt(missions[0], "THEME_REVIEW", at(WEEK.plusDays(5)))
        com.sagomungchi.learning._common.security.UserContextHolder.set(
            com.sagomungchi.learning._common.security.UserContext(null, "SYSTEM", setOf(student.toString()), null))
        try {
            val summary = reports.summary(student, WEEK)
            assertNull(summary.reviewRetries.single().comparison)
        } finally {
            com.sagomungchi.learning._common.security.UserContextHolder.clear()
        }
    }

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit) {
        val error = assertThrows<RuntimeException> { block() }
        assertEquals(status to code, httpStatusOf(error) to errorCodeOf(error))
    }

    @Test
    fun `수요일에는 월·화 CLOSED, 수 OPEN, 목·금 LOCKED이고 소개는 월요일에만`() {
        val wednesday = WEEK.plusDays(2)
        attempt(missions[0], "THEME_DAY", at(WEEK), at(WEEK, 11), at(WEEK, 12))
        attempt(missions[2], "THEME_DAY", at(wednesday))

        val view = serviceOn(wednesday).current(student, ThemeGrade.G3, wednesday)

        assertEquals(themeId to WEEK, view.themeId to view.weekStart)
        assertEquals("물의 여행", view.title)
        assertNull(view.intro)
        assertFalse(view.reused)
        assertEquals(ThemeDay.entries, view.days.map { it.day })
        assertEquals(missions.map { it.id }, view.days.map { it.missionId })
        assertEquals(listOf(DayState.CLOSED, DayState.CLOSED, DayState.OPEN, DayState.LOCKED, DayState.LOCKED), view.days.map { it.state })
        assertEquals(listOf("COMPLETED", "NOT_STARTED", "IN_PROGRESS", "NOT_STARTED", "NOT_STARTED"), view.days.map { it.attemptStatus })
        assertEquals("ANALYZE", view.days.first().thinkingType.name)
        assertFalse(view.review.open)
        assertEquals(listOf(true, false, false, false, false), view.review.missions.map { it.completed })
        assertEquals(listOf(false, true, false, false, false), view.review.missions.map { it.missed })
        assertFalse(view.completed)
        assertEquals("이번 주는 물", serviceOn(WEEK).current(student, ThemeGrade.G3, WEEK).intro)
    }

    @Test
    fun `그 주 게시 테마가 없으면 최근 게시 테마를 다시 쓰고, 지난주 시도는 이번 주 상태에 넣지 않음`() {
        attempt(missions[0], "THEME_DAY", at(WEEK), at(WEEK), at(WEEK))
        val nextMonday = WEEK.plusWeeks(1)

        val view = serviceOn(nextMonday).current(student, ThemeGrade.G3, nextMonday)

        assertEquals(themeId to nextMonday, view.themeId to view.weekStart)
        assertTrue(view.reused)
        assertEquals("NOT_STARTED", view.days.first().attemptStatus)
        assertEquals(DayState.OPEN, view.days.first().state)
    }

    @Test
    fun `학년에 게시 테마가 하나도 없거나 미래 주 테마만 있으면 404`() {
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { serviceOn(WEEK).current(student, ThemeGrade.G5, WEEK) }
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { serviceOn(WEEK).current(student, ThemeGrade.G3, WEEK.minusWeeks(1)) }
    }

    @Test
    fun `THEME_DAY는 오늘 요일 문제만, 다른 요일·토요일·다른 학년은 409 THEME_DAY_CLOSED`() {
        val wednesday = WEEK.plusDays(2)
        val service = serviceOn(wednesday)

        assertEquals(ThemeAttempt(themeId, WEEK), service.checkStart(student, missions[2].id, 3, AttemptContext.THEME_DAY))
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { service.checkStart(student, missions[1].id, 3, AttemptContext.THEME_DAY) }
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { service.checkStart(student, missions[2].id, 5, AttemptContext.THEME_DAY) }
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") {
            serviceOn(WEEK.plusDays(5)).checkStart(student, missions[4].id, 3, AttemptContext.THEME_DAY)
        }
    }

    @Test
    fun `THEME_REVIEW는 토·일에 이번 주 마무리한 문제만, 놓친 문제·평일은 409 THEME_REVIEW_NOT_ALLOWED`() {
        attempt(missions[0], "THEME_DAY", at(WEEK), finishedAt = at(WEEK, 11))
        attempt(missions[1], "THEME_DAY", at(WEEK.plusDays(1)))
        val saturday = serviceOn(WEEK.plusDays(5))

        assertEquals(ThemeAttempt(themeId, WEEK), saturday.checkStart(student, missions[0].id, 3, AttemptContext.THEME_REVIEW))
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { saturday.checkStart(student, missions[1].id, 3, AttemptContext.THEME_REVIEW) }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { saturday.checkStart(student, missions[2].id, 3, AttemptContext.THEME_REVIEW) }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") {
            saturday.checkStart(student, rows.mission().id, 3, AttemptContext.THEME_REVIEW)
        }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") {
            serviceOn(WEEK.plusDays(4)).checkStart(student, missions[0].id, 3, AttemptContext.THEME_REVIEW)
        }
    }

    @Test
    fun `되돌아보기 열람은 토·일만, 주 1회 멱등이고 완주는 다섯 문제를 각 요일 안에 학습 완료`() {
        ThemeDay.entries.forEach { day ->
            val date = day.dateIn(WEEK)
            // 금요일 문제는 자정을 넘겨 토요일 01시에 완료: 완주 아님
            val completed = if (day == ThemeDay.FRI) at(date.plusDays(1), 1) else at(date, 12)
            attempt(missions[day.number - 1], "THEME_DAY", at(date), at(date, 11), completed)
        }
        val sunday = WEEK.plusDays(6)

        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { serviceOn(WEEK).recordReviewView(student, ThemeGrade.G3, WEEK) }
        val first = serviceOn(sunday).recordReviewView(student, ThemeGrade.G3, sunday)
        val again = serviceOn(sunday).recordReviewView(student, ThemeGrade.G3, WEEK.plusDays(5))

        assertTrue(first.firstViewThisWeek)
        assertFalse(again.firstViewThisWeek)
        assertFalse(first.completed)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM theme_review_view WHERE student_id = ?", Int::class.java, student))

        jdbc.update("UPDATE attempt SET completed_at = ? WHERE mission_id = ?", at(WEEK.plusDays(4), 20), missions[4].id)
        assertTrue(serviceOn(sunday).recordReviewView(student, ThemeGrade.G3, sunday).completed)
        assertTrue(serviceOn(sunday).current(student, ThemeGrade.G3, sunday).completed)
        assertTrue(serviceOn(sunday).current(student, ThemeGrade.G3, sunday).review.open)
    }

    @Test
    fun `주간 요약은 테마 시도가 없으면 NO_RECORD, 있으면 요일별 완료와 되돌아보기 다시 풀기`() {
        val service = serviceOn(WEEK.plusDays(7))
        // 같은 트랜잭션의 같은 조회는 MyBatis 세션 캐시를 타므로 시도 없는 학생은 다른 학생으로 확인
        assertEquals(ThemeSummaryState.NO_RECORD, service.summary(UUID.randomUUID(), WEEK).state)

        attempt(missions[0], "THEME_DAY", at(WEEK), at(WEEK, 11), at(WEEK, 12))
        attempt(missions[1], "THEME_DAY", at(WEEK.plusDays(1)), at(WEEK.plusDays(1), 11), at(WEEK.plusDays(2), 9))
        val retry = attempt(missions[0], "THEME_REVIEW", at(WEEK.plusDays(5)))

        val summary = service.summary(student, WEEK)

        assertEquals(ThemeSummaryState.OK to themeId, summary.state to summary.themeId)
        assertEquals("물의 여행", summary.title)
        assertEquals(listOf(true, false, false, false, false), summary.days.map { it.completed })
        assertFalse(summary.completed)
        assertEquals(listOf(retry), summary.reviewRetries.map { it.attemptId })
        assertEquals("테마 1", summary.reviewRetries.single().title)
        assertEquals(ThemeSummaryState.NO_RECORD, service.summary(student, WEEK.plusWeeks(1)).state)
    }

    private companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        /** 2026-11-09 월요일 */
        val WEEK: LocalDate = LocalDate.of(2026, 11, 9)
    }
}
