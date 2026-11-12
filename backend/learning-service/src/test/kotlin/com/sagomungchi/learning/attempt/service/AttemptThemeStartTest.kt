package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning.TestAssets
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.domain.AttemptContext
import com.sagomungchi.learning.attempt.repository.AttemptDraftRepository
import com.sagomungchi.learning.attempt.repository.AttemptRepository
import com.sagomungchi.learning.judgment.service.JudgmentService
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.theme.domain.DialogueLine
import com.sagomungchi.learning.theme.domain.HintSpot
import com.sagomungchi.learning.theme.repository.WeeklyThemeRepository
import com.sagomungchi.learning.theme.service.WeeklyThemeService
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Clock
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 시도 시작 컨텍스트 (#385, api-spec 2.11): 신규 시도만 요일·되돌아보기 검사, 진행 중 시도는 검사 없이 이어함 */
class AttemptThemeStartTest : PostgresRepositoryTest() {
    @Autowired lateinit var attemptRepository: AttemptRepository
    @Autowired lateinit var draftRepository: AttemptDraftRepository
    @Autowired lateinit var missionService: MissionService
    @Autowired lateinit var judgmentService: JudgmentService
    @Autowired lateinit var themeRepository: WeeklyThemeRepository
    @Autowired lateinit var themeFrameService: com.sagomungchi.learning.memory.service.ThemeFrameService
    @Autowired lateinit var jdbc: JdbcTemplate

    private lateinit var missions: List<TestRows.SeededMission>
    private lateinit var themeId: UUID
    private val student = UUID.randomUUID()

    @BeforeEach
    fun seed() {
        val rows = TestRows(jdbc)
        missions = rows.themeMissions()
        themeId = rows.publishedTheme(missions.map { it.id }, WEEK)
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    /** 그 날짜 KST 정오의 시계를 쓰는 시도 서비스 */
    private fun on(date: LocalDate) = AttemptService(
        attemptRepository, draftRepository, missionService, judgmentService,
        WeeklyThemeService(themeRepository, Clock.fixed(date.atTime(12, 0).atZone(KST).toInstant(), KST), com.sagomungchi.learning.TestAssets.urls),
        themeFrameService,
    )

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit) {
        val error = assertThrows<RuntimeException> { block() }
        assertEquals(status to code, httpStatusOf(error) to errorCodeOf(error))
    }

    @Test
    fun `테마 시도 응답에 그 미션 요일의 대화·생각 열기 위치·문제 전 영상, EXTRA는 null (#438)`() {
        jdbc.update(
            """UPDATE weekly_theme_day SET dialogue = '[{"speaker":"뭉치","text":"어디 갔을까?"}]'::jsonb,
                   hint_spots = '[{"seq":1,"x":10.0,"y":20.0}]'::jsonb, video_uri = 'theme-drafts/run/TUE.mp4'
               WHERE day_of_week = 2 AND theme_version_id = (SELECT published_version_id FROM weekly_theme WHERE id = ?)""",
            themeId,
        )
        val tuesday = on(WEEK.plusDays(1))
        val themed = tuesday.start(student, missions[1].id, 3, false, AttemptContext.THEME_DAY).attempt
        val extra = tuesday.start(student, missions[3].id, 3, false).attempt
        val scene = checkNotNull(tuesday.get(themed.id).themeScene)
        assertEquals(listOf(DialogueLine("뭉치", "어디 갔을까?")), scene.dialogue)
        assertEquals(listOf(HintSpot(1, 10.0, 20.0)), scene.hintSpots)
        assertTrue(scene.videoUrl!!.startsWith(TestAssets.BASE + "theme-drafts/run/TUE.mp4?"), scene.videoUrl)
        assertNull(tuesday.get(extra.id).themeScene)
    }

    @Test
    fun `THEME_DAY는 공개된 요일 문제면 그 주 테마를 시도에 저장하고, 공개 전 문제는 409 (#484)`() {
        val tuesday = on(WEEK.plusDays(1))

        val started = tuesday.start(student, missions[1].id, 3, false, AttemptContext.THEME_DAY)
        // 누적 공개: 화요일에 월요일 문제도 새로 시작
        val monday = tuesday.start(student, missions[0].id, 3, false, AttemptContext.THEME_DAY)

        assertTrue(started.created)
        assertTrue(monday.created)
        assertEquals(Triple(AttemptContext.THEME_DAY, themeId, WEEK), Triple(started.attempt.context, started.attempt.themeId, started.attempt.themeWeekStart))
        assertEquals(listOf("THEME_DAY", themeId.toString(), WEEK.toString()), jdbc.queryForList(
            "SELECT context, theme_id::text AS theme, theme_week_start::text AS week FROM attempt WHERE id = ?", started.attempt.id,
        ).single().values.map { it.toString() })
        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { tuesday.start(student, missions[2].id, 3, false, AttemptContext.THEME_DAY) }
    }

    @Test
    fun `일요일 THEME_DAY는 core 허용 값 sundayTheme이 true일 때만 (#484)`() {
        val sunday = on(WEEK.plusDays(6))

        assertError(HttpStatus.CONFLICT, "THEME_DAY_CLOSED") { sunday.start(student, missions[4].id, 3, false, AttemptContext.THEME_DAY) }
        val started = sunday.start(student, missions[4].id, 3, false, AttemptContext.THEME_DAY, sundayTheme = true)

        assertTrue(started.created)
        assertEquals(AttemptContext.THEME_DAY to WEEK, started.attempt.context to started.attempt.themeWeekStart)
    }

    @Test
    fun `진행 중 시도는 자정이 지나 요일이 바뀌어도 검사 없이 원래 컨텍스트로 이어함`() {
        val started = on(WEEK).start(student, missions[0].id, 3, false, AttemptContext.THEME_DAY)

        val resumed = on(WEEK.plusDays(1)).start(student, missions[0].id, 3, false, AttemptContext.THEME_DAY)
        val asExtra = on(WEEK.plusDays(1)).start(student, missions[0].id, 3, false)

        assertFalse(resumed.created)
        assertEquals(started.attempt.id, resumed.attempt.id)
        assertEquals(started.attempt.id to AttemptContext.THEME_DAY, asExtra.attempt.id to asExtra.attempt.context)
    }

    @Test
    fun `THEME_REVIEW는 토요일에 그 주 마무리한 문제만 새 시도, EXTRA는 테마 없이 그대로`() {
        val monday = on(WEEK).start(student, missions[0].id, 3, false, AttemptContext.THEME_DAY).attempt
        jdbc.update("UPDATE attempt SET finished_at = now(), status = 'COMPLETED', completed_at = now() WHERE id = ?", monday.id)
        val saturday = on(WEEK.plusDays(5))

        val retry = saturday.start(student, missions[0].id, 3, false, AttemptContext.THEME_REVIEW)
        val extra = saturday.start(student, missions[3].id, 3, false)

        assertEquals(Triple(AttemptContext.THEME_REVIEW, themeId, WEEK), Triple(retry.attempt.context, retry.attempt.themeId, retry.attempt.themeWeekStart))
        assertEquals(AttemptContext.EXTRA, extra.attempt.context)
        assertNull(extra.attempt.themeId)
        assertError(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED") { saturday.start(student, missions[1].id, 3, false, AttemptContext.THEME_REVIEW) }
        // #438: 다시 풀기 시도도 그 미션 요일(월)의 장면을 받음(요일 칸이 비어 모두 null), EXTRA는 null
        assertEquals(com.sagomungchi.learning.theme.domain.ThemeScene(null, null, null), saturday.get(retry.attempt.id).themeScene)
        assertNull(saturday.get(extra.attempt.id).themeScene)
    }

    @Test
    fun `미션 공개·학년 범위 검사가 요일 검사보다 먼저`() {
        jdbc.update("UPDATE mission SET status = 'UNPUBLISHED' WHERE id = ?", missions[0].id)

        assertError(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE") { on(WEEK).start(student, missions[0].id, 3, false, AttemptContext.THEME_DAY) }
    }

    @Test
    fun `DB는 테마 컨텍스트인데 테마가 없는 시도를 거부`() {
        val mission = missions[0]
        fun insert(context: String, theme: UUID?, week: LocalDate?) = jdbc.update(
            """INSERT INTO attempt (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status, started_at, updated_at,
                   context, theme_id, theme_week_start) VALUES (?, ?, ?, ?, ?, 3, 'COMPLETED', now(), now(), ?, ?, ?)""",
            UUID.randomUUID(), student, mission.id, mission.versionId, mission.rubricVersionId, context, theme, week,
        )
        assertThrows<org.springframework.dao.DataIntegrityViolationException> { insert("THEME_DAY", null, null) }
    }

    private companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        val WEEK: LocalDate = LocalDate.of(2026, 11, 9)
    }
}
