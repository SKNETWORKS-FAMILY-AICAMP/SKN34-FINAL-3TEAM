package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning.TestAssets
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.attempt.domain.AttemptContext
import com.sagomungchi.learning.attempt.domain.ThemeAttempt
import com.sagomungchi.learning.theme.domain.AnswerPickResult
import com.sagomungchi.learning.theme.domain.DayState
import com.sagomungchi.learning.theme.domain.ThemeEndingState
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeStoryKind
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
        WeeklyThemeService(repository, Clock.fixed(date.atTime(12, 0).atZone(KST).toInstant(), KST), TestAssets.urls)

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
    fun `수요일에는 월~수 OPEN(누적 공개), 목·금 LOCKED이고 소개는 매일 (#484)`() {
        val wednesday = WEEK.plusDays(2)
        attempt(missions[0], "THEME_DAY", at(WEEK), at(WEEK, 11), at(WEEK, 12))
        attempt(missions[2], "THEME_DAY", at(wednesday))

        val view = serviceOn(wednesday).current(student, ThemeGrade.G3, wednesday)

        assertEquals(themeId to WEEK, view.themeId to view.weekStart)
        assertEquals("물의 여행", view.title)
        assertEquals("이번 주는 물", view.intro) // #438: 시작 이야기를 그 주 첫 진입에 보여 주려고 매일 채움
        assertFalse(view.reused)
        assertEquals(ThemeDay.entries, view.days.map { it.day })
        assertEquals(missions.map { it.id }, view.days.map { it.missionId })
        assertEquals(listOf(DayState.OPEN, DayState.OPEN, DayState.OPEN, DayState.LOCKED, DayState.LOCKED), view.days.map { it.state })
        assertEquals(listOf("COMPLETED", "NOT_STARTED", "IN_PROGRESS", "NOT_STARTED", "NOT_STARTED"), view.days.map { it.attemptStatus })
        assertEquals("ANALYZE", view.days.first().thinkingType.name)
        assertFalse(view.review.open)
        assertEquals(listOf(true, false, false, false, false), view.review.missions.map { it.completed })
        // missed = 공개됐지만 아직 마무리하지 않음(진행 중 포함)
        assertEquals(listOf(false, true, true, false, false), view.review.missions.map { it.missed })
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
    fun `THEME_DAY는 공개된 문제를 토요일까지, 공개 전·무료 일요일·다른 학년·마무리한 문제는 409 THEME_DAY_CLOSED (#484)`() {
        val wednesday = WEEK.plusDays(2)
        val service = serviceOn(wednesday)
        val sunday = WEEK.plusDays(6)

        // 화요일에 월요일 문제처럼 지난 요일 문제도 공개됐으면 시작
        assertEquals(ThemeAttempt(themeId, WEEK), service.checkStart(student, missions[2].id, 3, AttemptContext.THEME_DAY))
        assertEquals(ThemeAttempt(themeId, WEEK), service.checkStart(student, missions[1].id, 3, AttemptContext.THEME_DAY))
        assertEquals(ThemeAttempt(themeId, WEEK), serviceOn(WEEK.plusDays(1)).checkStart(student, missions[0].id, 3, AttemptContext.THEME_DAY))
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { service.checkStart(student, missions[3].id, 3, AttemptContext.THEME_DAY) }
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { service.checkStart(student, missions[2].id, 5, AttemptContext.THEME_DAY) }
        // 토요일에는 안 푼 문제 새로 시작
        assertEquals(ThemeAttempt(themeId, WEEK), serviceOn(WEEK.plusDays(5)).checkStart(student, missions[4].id, 3, AttemptContext.THEME_DAY))
        // 일요일은 core 허용 값(프리미엄)이 있을 때만
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { serviceOn(sunday).checkStart(student, missions[4].id, 3, AttemptContext.THEME_DAY) }
        assertEquals(
            ThemeAttempt(themeId, WEEK),
            serviceOn(sunday).checkStart(student, missions[4].id, 3, AttemptContext.THEME_DAY, sundayTheme = true),
        )
        // 그 주에 이미 마무리한 문제는 새 THEME_DAY 대신 토요일 THEME_REVIEW로(#506). 마무리 전 시도만 있으면 시작 가능.
        // 같은 트랜잭션의 같은 조회는 MyBatis 세션 캐시를 타므로 시도가 있는 학생은 다른 학생으로 확인
        val solver = UUID.randomUUID()
        attempt(missions[0], "THEME_DAY", at(WEEK), finishedAt = at(WEEK, 11), studentId = solver)
        attempt(missions[1], "THEME_DAY", at(WEEK.plusDays(1)), studentId = solver)
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { service.checkStart(solver, missions[0].id, 3, AttemptContext.THEME_DAY) }
        assertEquals(ThemeAttempt(themeId, WEEK), service.checkStart(solver, missions[1].id, 3, AttemptContext.THEME_DAY))
        // 지난주에 마무리한 시도는 이번 주 "마무리"에 들지 않음(재사용 테마)
        val nextWednesday = wednesday.plusWeeks(1)
        assertEquals(
            ThemeAttempt(themeId, WEEK.plusWeeks(1)),
            serviceOn(nextWednesday).checkStart(solver, missions[0].id, 3, AttemptContext.THEME_DAY),
        )
    }

    @Test
    fun `THEME_REVIEW는 토요일·프리미엄 일요일에 이번 주 마무리한 문제만, 놓친 문제·평일·무료 일요일은 409 (#484)`() {
        attempt(missions[0], "THEME_DAY", at(WEEK), finishedAt = at(WEEK, 11))
        attempt(missions[1], "THEME_DAY", at(WEEK.plusDays(1)))
        val saturday = serviceOn(WEEK.plusDays(5))
        val sunday = serviceOn(WEEK.plusDays(6))

        assertEquals(ThemeAttempt(themeId, WEEK), saturday.checkStart(student, missions[0].id, 3, AttemptContext.THEME_REVIEW))
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { saturday.checkStart(student, missions[1].id, 3, AttemptContext.THEME_REVIEW) }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { saturday.checkStart(student, missions[2].id, 3, AttemptContext.THEME_REVIEW) }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") {
            saturday.checkStart(student, rows.mission().id, 3, AttemptContext.THEME_REVIEW)
        }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") {
            serviceOn(WEEK.plusDays(4)).checkStart(student, missions[0].id, 3, AttemptContext.THEME_REVIEW)
        }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { sunday.checkStart(student, missions[0].id, 3, AttemptContext.THEME_REVIEW) }
        assertEquals(
            ThemeAttempt(themeId, WEEK),
            sunday.checkStart(student, missions[0].id, 3, AttemptContext.THEME_REVIEW, sundayTheme = true),
        )
    }

    @Test
    fun `일요일 요일 상태는 무료면 모두 CLOSED, 프리미엄이면 OPEN이고 되돌아보기도 프리미엄만 열림 (#484)`() {
        val sunday = WEEK.plusDays(6)

        val free = serviceOn(sunday).current(student, ThemeGrade.G3, sunday)
        val premium = serviceOn(sunday).current(student, ThemeGrade.G3, sunday, sundayTheme = true)
        val saturday = serviceOn(WEEK.plusDays(5)).current(student, ThemeGrade.G3, WEEK.plusDays(5))

        assertEquals(List(5) { DayState.CLOSED }, free.days.map { it.state })
        assertFalse(free.review.open)
        assertEquals(List(5) { DayState.OPEN }, premium.days.map { it.state })
        assertTrue(premium.review.open)
        assertEquals(List(5) { DayState.OPEN }, saturday.days.map { it.state })
        assertTrue(saturday.review.open)
        // 평일·토요일에는 허용 값과 무관
        assertEquals(
            serviceOn(WEEK).current(student, ThemeGrade.G3, WEEK).days.map { it.state },
            serviceOn(WEEK).current(student, ThemeGrade.G3, WEEK, sundayTheme = true).days.map { it.state },
        )
    }

    @Test
    fun `되돌아보기 열람은 토요일·프리미엄 일요일만, 주 1회 멱등이고 개근은 다섯 문제를 각 요일 안에 학습 완료 (#484)`() {
        ThemeDay.entries.forEach { day ->
            val date = day.dateIn(WEEK)
            // 금요일 문제는 자정을 넘겨 토요일 01시에 완료: 개근 아님
            val completed = if (day == ThemeDay.FRI) at(date.plusDays(1), 1) else at(date, 12)
            attempt(missions[day.number - 1], "THEME_DAY", at(date), at(date, 11), completed)
        }
        val saturday = WEEK.plusDays(5)
        val sunday = WEEK.plusDays(6)

        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { serviceOn(WEEK).recordReviewView(student, ThemeGrade.G3, WEEK) }
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { serviceOn(sunday).recordReviewView(student, ThemeGrade.G3, sunday) }
        val first = serviceOn(saturday).recordReviewView(student, ThemeGrade.G3, saturday)
        val again = serviceOn(sunday).recordReviewView(student, ThemeGrade.G3, sunday, sundayTheme = true)

        assertTrue(first.firstViewThisWeek)
        assertFalse(again.firstViewThisWeek)
        assertFalse(first.completed)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM theme_review_view WHERE student_id = ?", Int::class.java, student))

        jdbc.update("UPDATE attempt SET completed_at = ? WHERE mission_id = ?", at(WEEK.plusDays(4), 20), missions[4].id)
        assertTrue(serviceOn(saturday).recordReviewView(student, ThemeGrade.G3, saturday).completed)
        assertTrue(serviceOn(sunday).current(student, ThemeGrade.G3, sunday).completed)
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

    /** 게시 테마에 이야기·정답 구조·요일 단서를 넣음 (화·목·금에 틀린 후보를 하나씩 뺌) */
    private fun addStory() {
        val versionId = jdbc.queryForObject("SELECT published_version_id FROM weekly_theme WHERE id = ?", UUID::class.java, themeId)
        jdbc.update(
            """UPDATE weekly_theme_version SET outro = '강아지는 이웃집에 있었어요', intro_image_uri = 'theme-drafts/run/INTRO.png',
                   outro_image_uri = 'theme-drafts/run/OUTRO.png', outro_video_uri = 'theme-drafts/run/OUTRO.mp4',
                   intro_motion = '{"zoom":1.1}'::jsonb, outro_motion = '{"pan":"left"}'::jsonb, big_question = '강아지는 어디에 있을까?',
                   candidates = '["고양이","강아지","토끼","햄스터"]'::jsonb, answer = '강아지', answer_clue = '금요일 단서'
               WHERE id = ?""",
            versionId,
        )
        val out = mapOf(2 to "[\"토끼\"]", 4 to "[\"고양이\"]", 5 to "[\"햄스터\"]")
        (1..5).forEach { day ->
            jdbc.update(
                "UPDATE weekly_theme_day SET clue = ?, rules_out = ?::jsonb WHERE theme_version_id = ? AND day_of_week = ?",
                "단서 $day", out[day] ?: "[]", versionId, day,
            )
        }
    }

    @Test
    fun `요일 단서는 그 문제를 학습 완료한 뒤, 결말·정답은 엔딩 전에는 토요일에도 없음 (#484)`() {
        addStory()
        val wednesday = WEEK.plusDays(2)
        // 월요일 문제는 학습 완료, 화요일 문제는 마무리만(돌아보기 전), 수요일 문제는 진행 중
        attempt(missions[0], "THEME_DAY", at(WEEK), at(WEEK, 11), at(WEEK, 12))
        attempt(missions[1], "THEME_DAY", at(WEEK.plusDays(1)), at(WEEK.plusDays(1), 11))
        attempt(missions[2], "THEME_DAY", at(wednesday))
        val view = serviceOn(wednesday).current(student, ThemeGrade.G3, wednesday)

        assertEquals("강아지는 어디에 있을까?" to listOf("고양이", "강아지", "토끼", "햄스터"), view.bigQuestion to view.candidates)
        assertEquals(listOf("단서 1", null, null, null, null), view.days.map { it.clue })
        assertEquals(listOf(emptyList(), null, null, null, null), view.days.map { it.rulesOut })
        assertTrue(view.introImageUrl!!.startsWith(TestAssets.BASE + "theme-drafts/run/INTRO.png?"), view.introImageUrl)
        assertEquals(mapOf("zoom" to 1.1), view.introMotion)
        assertNull(view.introVideoUrl)
        assertEquals(ThemeEndingState.NOT_ENDED, view.ending)
        listOf(view.outro, view.outroImageUrl, view.outroVideoUrl, view.outroMotion, view.answer, view.answerClue).forEach { assertNull(it) }

        // 정답을 고르지 않았으면 토요일에도 엔딩 아님
        val saturday = WEEK.plusDays(5)
        val notEnded = serviceOn(saturday).current(student, ThemeGrade.G3, saturday)
        assertEquals(ThemeEndingState.NOT_ENDED, notEnded.ending)
        assertNull(notEnded.answer)
        assertNull(notEnded.outro)
    }

    @Test
    fun `금요일 문제를 마무리한 뒤 정답을 맞히면 바로 엔딩이고 결말·정답·결정적 단서를 줌 (#484)`() {
        addStory()
        val friday = WEEK.plusDays(4)
        val service = serviceOn(friday)
        // 금요일 문제를 마무리하지 않은 학생은 고를 수 없음(같은 조회의 세션 캐시를 피하려고 다른 학생)
        assertError(HttpStatus.CONFLICT, "THEME_PICK_NOT_ALLOWED") { service.pickAnswer(UUID.randomUUID(), ThemeGrade.G3, friday, "강아지") }
        attempt(missions[4], "THEME_DAY", at(friday, 9), finishedAt = at(friday, 10))

        assertError(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED") { service.pickAnswer(student, ThemeGrade.G3, friday, "거북이") }
        val picked = service.pickAnswer(student, ThemeGrade.G3, friday, "강아지")

        assertEquals(AnswerPickResult(true, ThemeEndingState.ENDED, "강아지"), picked)
        assertError(HttpStatus.CONFLICT, "THEME_PICK_NOT_ALLOWED") { service.pickAnswer(student, ThemeGrade.G3, friday, "고양이") }
        val ended = service.current(student, ThemeGrade.G3, friday)
        assertEquals(ThemeEndingState.ENDED, ended.ending)
        assertEquals("강아지는 이웃집에 있었어요" to "강아지", ended.outro to ended.answer)
        assertEquals("금요일 단서", ended.answerClue)
        assertTrue(ended.outroVideoUrl!!.startsWith(TestAssets.BASE + "theme-drafts/run/OUTRO.mp4?"), ended.outroVideoUrl)
        assertEquals(mapOf("pan" to "left"), ended.outroMotion)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM theme_answer_pick WHERE student_id = ?", Int::class.java, student))
        // 무료 일요일에도 이미 본 엔딩은 다시 볼 수 있음
        val sunday = WEEK.plusDays(6)
        assertEquals("강아지", serviceOn(sunday).current(student, ThemeGrade.G3, sunday).answer)
    }

    @Test
    fun `정답을 틀리면 토요일 금요일 문제 다시 풀기를 마무리한 뒤 엔딩, 고르기 전 다시 풀기는 세지 않음 (#484)`() {
        addStory()
        val friday = WEEK.plusDays(4)
        val saturday = WEEK.plusDays(5)
        attempt(missions[4], "THEME_DAY", at(friday, 9), finishedAt = at(friday, 10), completedAt = at(friday, 10))
        // 고르기(금요일 정오) 전에 마무리한 다시 풀기는 엔딩 조건이 아님
        attempt(missions[4], "THEME_REVIEW", at(friday, 10), finishedAt = at(friday, 11), completedAt = at(friday, 11))

        val picked = serviceOn(friday).pickAnswer(student, ThemeGrade.G3, friday, "고양이")

        assertEquals(AnswerPickResult(false, ThemeEndingState.NOT_ENDED, null), picked)
        assertEquals(ThemeEndingState.NOT_ENDED, serviceOn(saturday).ending(student, WEEK))
        attempt(missions[4], "THEME_REVIEW", at(saturday, 13), finishedAt = at(saturday, 14), completedAt = at(saturday, 14))
        // 같은 트랜잭션의 같은 조회는 MyBatis 세션 캐시를 타므로 쓰기 한 번으로 비움
        serviceOn(saturday).recordReviewView(student, ThemeGrade.G3, saturday)
        val ended = serviceOn(saturday).current(student, ThemeGrade.G3, saturday)
        assertEquals(ThemeEndingState.ENDED, ended.ending)
        assertEquals("강아지", ended.answer)
    }

    @Test
    fun `정답 고르기는 큰 질문 없는 테마·무료 일요일·다른 학년 테마에서 거부 (#484)`() {
        val friday = WEEK.plusDays(4)
        attempt(missions[4], "THEME_DAY", at(friday, 9), finishedAt = at(friday, 10))
        // 큰 질문이 없는 테마(같은 미션으로 게시한 G4 테마, 기본 미션은 3~4학년)
        rows.publishedTheme(missions.map { it.id }, WEEK, grade = "G4", title = "큰 질문 없는 테마")
        assertError(HttpStatus.CONFLICT, "THEME_PICK_NOT_ALLOWED") { serviceOn(friday).pickAnswer(student, ThemeGrade.G4, friday, "강아지") }
        addStory()
        val sunday = WEEK.plusDays(6)
        assertError(HttpStatus.CONFLICT, "THEME_PICK_NOT_ALLOWED") { serviceOn(sunday).pickAnswer(student, ThemeGrade.G3, sunday, "강아지") }
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { serviceOn(friday).pickAnswer(student, ThemeGrade.G5, friday, "강아지") }
        // 프리미엄 일요일에는 고를 수 있음
        assertEquals(true, serviceOn(sunday).pickAnswer(student, ThemeGrade.G3, sunday, "강아지", sundayTheme = true).correct)
    }

    @Test
    fun `당일 풀이는 그 요일 안의 학습 완료, 주간 완주는 토요일까지 다섯 문제 학습 완료이고 일요일 완료는 빼고 요약에도 같음 (#484·#486)`() {
        // 월: 당일 완료, 화: 수요일에 완료, 수·목: 토요일에 완료, 금: 다시 풀기로 토요일에 학습 완료(요일 시도는 마무리만)
        attempt(missions[0], "THEME_DAY", at(WEEK), at(WEEK, 11), at(WEEK, 12))
        attempt(missions[1], "THEME_DAY", at(WEEK.plusDays(1)), at(WEEK.plusDays(1), 11), at(WEEK.plusDays(2), 9))
        attempt(missions[2], "THEME_DAY", at(WEEK.plusDays(5)), at(WEEK.plusDays(5), 11), at(WEEK.plusDays(5), 12))
        attempt(missions[3], "THEME_DAY", at(WEEK.plusDays(5)), at(WEEK.plusDays(5), 11), at(WEEK.plusDays(5), 23))
        attempt(missions[4], "THEME_DAY", at(WEEK.plusDays(4)), at(WEEK.plusDays(4), 11))
        attempt(missions[4], "THEME_REVIEW", at(WEEK.plusDays(5)), at(WEEK.plusDays(5), 11), at(WEEK.plusDays(5), 12))
        val sunday = WEEK.plusDays(6)

        val view = serviceOn(sunday).current(student, ThemeGrade.G3, sunday)
        val summary = serviceOn(sunday).summary(student, WEEK)

        assertEquals(listOf(true, false, false, false, false), view.days.map { it.completedOnDay })
        assertFalse(view.completed)
        assertTrue(view.finished)
        assertEquals(listOf(true, false, false, false, false), summary.days.map { it.completed })
        assertEquals(List(5) { true }, summary.days.map { it.completedInWeek })
        assertTrue(summary.finished)
        assertEquals(ThemeEndingState.NOT_ENDED, summary.ending)
    }

    @Test
    fun `일요일에 끝낸 문제가 있으면 주간 완주가 아니고 요약의 그 요일은 나중에 풀었어요 (#484·#486)`() {
        ThemeDay.entries.forEach { day ->
            val date = day.dateIn(WEEK)
            val completed = if (day == ThemeDay.FRI) at(date.plusDays(2), 10) else at(date, 12)
            attempt(missions[day.number - 1], "THEME_DAY", at(date), at(date, 11), completed)
        }
        val summary = serviceOn(WEEK.plusDays(7)).summary(student, WEEK)

        assertFalse(summary.finished)
        assertFalse(summary.completed)
        assertEquals(listOf(true, true, true, true, false), summary.days.map { it.completed })
        assertEquals(List(5) { true }, summary.days.map { it.completedInWeek })
        assertFalse(serviceOn(WEEK.plusDays(7)).summary(UUID.randomUUID(), WEEK).finished)
    }

    @Test
    fun `정답 고르기 문제(큰 질문 테마의 금요일 문제)는 그 문제로 고른 주에 엔딩을 봐야 커뮤니티가 열림 (#484)`() {
        val friday = WEEK.plusDays(4)
        addStory()
        attempt(missions[4], "THEME_DAY", at(friday, 9), finishedAt = at(friday, 10))

        assertTrue(serviceOn(friday).lockedUntilEnding(student, missions[4].id))
        assertFalse(serviceOn(friday).lockedUntilEnding(student, missions[3].id))
        serviceOn(friday).pickAnswer(student, ThemeGrade.G3, friday, "고양이")
        assertTrue(serviceOn(friday).lockedUntilEnding(student, missions[4].id))
        // 다른 학생이 맞히면 그 학생은 열림
        val other = UUID.randomUUID()
        attempt(missions[4], "THEME_DAY", at(friday, 9), finishedAt = at(friday, 10), studentId = other)
        serviceOn(friday).pickAnswer(other, ThemeGrade.G3, friday, "강아지")
        assertFalse(serviceOn(friday).lockedUntilEnding(other, missions[4].id))
    }

    @Test
    fun `이야기 열람에서 INTRO는 월~토·프리미엄 일요일, OUTRO는 엔딩이고 무료 일요일이 아닐 때, 주 1회 멱등 (#438·#484)`() {
        addStory()
        attempt(missions[4], "THEME_DAY", at(WEEK.plusDays(4), 9), finishedAt = at(WEEK.plusDays(4), 10))
        val sunday = WEEK.plusDays(6)
        assertError(HttpStatus.CONFLICT, "THEME_STORY_NOT_ALLOWED") { serviceOn(sunday).recordStoryView(student, ThemeGrade.G3, sunday, ThemeStoryKind.INTRO) }
        // 프리미엄 일요일은 토요일과 같이 INTRO 기록(#484). 다른 학생으로 확인
        assertEquals(
            true,
            serviceOn(sunday).recordStoryView(UUID.randomUUID(), ThemeGrade.G3, sunday, ThemeStoryKind.INTRO, sundayTheme = true).firstViewThisWeek,
        )
        val thursday = WEEK.plusDays(3)
        assertEquals(true, serviceOn(thursday).recordStoryView(student, ThemeGrade.G3, thursday, ThemeStoryKind.INTRO).firstViewThisWeek)
        assertEquals(false, serviceOn(thursday).recordStoryView(student, ThemeGrade.G3, thursday, ThemeStoryKind.INTRO).firstViewThisWeek)
        // 엔딩 전에는 토요일에도 OUTRO 409
        assertError(HttpStatus.CONFLICT, "THEME_STORY_NOT_ALLOWED") {
            serviceOn(WEEK.plusDays(5)).recordStoryView(student, ThemeGrade.G3, WEEK.plusDays(5), ThemeStoryKind.OUTRO)
        }
        assertFalse(serviceOn(thursday).current(student, ThemeGrade.G3, thursday).outroSeen)

        // 금요일에 정답을 맞히면 바로 OUTRO 기록, 무료 일요일은 엔딩이어도 409
        val friday = WEEK.plusDays(4)
        serviceOn(friday).pickAnswer(student, ThemeGrade.G3, friday, "강아지")
        assertError(HttpStatus.CONFLICT, "THEME_STORY_NOT_ALLOWED") { serviceOn(sunday).recordStoryView(student, ThemeGrade.G3, sunday, ThemeStoryKind.OUTRO) }
        assertEquals(true, serviceOn(friday).recordStoryView(student, ThemeGrade.G3, friday, ThemeStoryKind.OUTRO).firstViewThisWeek)
        val saturday = WEEK.plusDays(5)
        assertEquals(false, serviceOn(saturday).recordStoryView(student, ThemeGrade.G3, saturday, ThemeStoryKind.OUTRO).firstViewThisWeek)
        val view = serviceOn(saturday).current(student, ThemeGrade.G3, saturday)
        assertEquals(true to true, view.introSeen to view.outroSeen)
        // 다음 주는 다시 처음
        assertFalse(serviceOn(WEEK.plusWeeks(1)).current(student, ThemeGrade.G3, WEEK.plusWeeks(1)).introSeen)
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { serviceOn(WEEK).recordStoryView(student, ThemeGrade.G5, WEEK, ThemeStoryKind.INTRO) }
    }

    private companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        /** 2026-11-09 월요일 */
        val WEEK: LocalDate = LocalDate.of(2026, 11, 9)
    }
}
