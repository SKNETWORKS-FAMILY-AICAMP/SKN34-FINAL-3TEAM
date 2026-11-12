package com.sagomungchi.learning.memory

import com.sagomungchi.learning.TestAssets
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.domain.Difficulty
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.attempt.repository.AttemptRepository
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.repository.ThemeFrameRepository
import com.sagomungchi.learning.memory.service.AlbumService
import com.sagomungchi.learning.memory.service.ThemeFrameService
import com.sagomungchi.learning.theme.domain.ThemeDay
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
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * 기념 액자·추억 앨범 (#559, P27, FN-RET-10·11): 5문제 완료 시 회차당 1개(일요일·자정 이어하기 인정, 다시 풀기 중복 없음, EXTRA 제외),
 * 소급 멱등, 앨범은 지난 주 보유 회차만, 엔딩 전 정답·종료 이야기 비노출
 */
class ThemeFrameTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var frameRepository: ThemeFrameRepository
    @Autowired lateinit var themeRepository: WeeklyThemeRepository
    @Autowired lateinit var attemptRepository: AttemptRepository
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var frameService: ThemeFrameService

    private lateinit var rows: TestRows
    private lateinit var missions: List<TestRows.SeededMission>
    private lateinit var themeId: UUID
    private val student = UUID.randomUUID()

    @BeforeEach
    fun seed() {
        rows = TestRows(jdbc)
        missions = rows.themeMissions()
        themeId = rows.publishedTheme(missions.map { it.id }, WEEK, title = "물의 여행")
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `다섯째 문제 학습 완료(돌아보기 저장) 트랜잭션에서 액자 1개, 획득 시각은 그 완료 시각이고 확인 전`() {
        (0..3).forEach { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        val fifth = attempt(missions[4], "THEME_DAY", finishedAt = at(WEEK.plusDays(4)))
        assertEquals(0, frames(student).size)

        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        attemptService.saveReflection(fifth, Reflection(Difficulty.EASY, "재미있었어"))

        val frame = frames(student).single()
        val completedAt = jdbc.queryForObject("SELECT completed_at FROM attempt WHERE id = ?", OffsetDateTime::class.java, fifth)
        assertEquals(themeId to WEEK, frame["theme_id"] to (frame["theme_week_start"] as java.sql.Date).toLocalDate())
        assertEquals(publishedVersion(), frame["theme_version_id"])
        assertEquals(completedAt!!.toInstant(), (frame["awarded_at"] as java.sql.Timestamp).toInstant())
        assertNull(frame["seen_at"])
    }

    @Test
    fun `4문제만 완료하면 액자 없음, 다섯째 문제를 EXTRA로 풀어도 회차 문제로 치지 않음`() {
        val done = (0..3).map { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        val extra = attempt(missions[4], "EXTRA", completedAt = at(WEEK.plusDays(4)), theme = null, week = null)

        assertFalse(frameService.awardIfComplete(load(done.last())))
        assertFalse(frameService.awardIfComplete(load(extra)))
        frameRepository.backfill(Instant.now())
        assertEquals(0, frames(student).size)
    }

    @Test
    fun `프리미엄 일요일 완료·자정 넘긴 이어하기 완료도 인정, 획득 시각은 문제별 처음 완료 중 가장 늦은 값`() {
        // 월요일 문제를 월요일 밤에 시작해 화요일 00:30에 완료(이어하기), 금요일 문제는 일요일에 완료(프리미엄 일요일)
        attempt(missions[0], "THEME_DAY", completedAt = at(WEEK.plusDays(1), 0, 30))
        (1..3).forEach { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        val sunday = attempt(missions[4], "THEME_DAY", completedAt = at(WEEK.plusDays(6), 15))

        assertTrue(frameService.awardIfComplete(load(sunday)))

        assertEquals(at(WEEK.plusDays(6), 15).toInstant(), awardedAt(student))
    }

    @Test
    fun `다시 풀기 완료는 새 액자를 만들지 않고 획득 시각·확인 상태 유지`() {
        val day = (0..4).map { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        assertTrue(frameService.awardIfComplete(load(day.last())))
        val before = frames(student)

        val retry = attempt(missions[2], "THEME_REVIEW", completedAt = at(WEEK.plusDays(5)))
        assertFalse(frameService.awardIfComplete(load(retry)))
        assertFalse(frameService.awardIfComplete(load(day.last())))

        assertEquals(before, frames(student))
        assertEquals(at(WEEK.plusDays(4)).toInstant(), awardedAt(student))
    }

    @Test
    fun `소급은 두 번 돌려도 같은 결과이고 빠진 회차만 확인 처리된 상태(확인 시각 = 획득 시각)로, 이미 받은 액자는 그대로`() {
        val earlier = UUID.randomUUID()
        (0..4).forEach { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong())), studentId = earlier) }
        val live = (0..4).map { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()), 11)) }
        assertTrue(frameService.awardIfComplete(load(live.last())))
        val liveBefore = frames(student)

        assertTrue(frameService.backfill() >= 1) // 같은 DB의 다른 커밋된 기록도 함께 채울 수 있음
        val first = frames(earlier) + frames(student)
        assertEquals(0, frameService.backfill())

        assertEquals(first, frames(earlier) + frames(student))
        assertEquals(liveBefore, frames(student))
        val backfilled = frames(earlier).single()
        assertEquals(at(WEEK.plusDays(4)).toInstant(), (backfilled["awarded_at"] as java.sql.Timestamp).toInstant())
        assertEquals(backfilled["awarded_at"], backfilled["seen_at"])
    }

    @Test
    fun `앨범은 지난 주 보유 회차만 최근순, 진행 중인 주 회차는 목록·상세·확인·보유 확인 모두 미보유`() {
        val nextWeek = WEEK.plusWeeks(1)
        val nextTheme = rows.publishedTheme(missions.map { it.id }, nextWeek, title = "숲의 소리")
        (0..4).forEach { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        (0..4).forEach { attempt(missions[it], "THEME_DAY", completedAt = at(nextWeek.plusDays(it.toLong())), theme = nextTheme, week = nextWeek) }
        frameRepository.backfill(Instant.now())
        jdbc.update("UPDATE theme_frame SET seen_at = NULL WHERE student_id = ? AND theme_id = ?", student, themeId)
        val past = RoundKey(themeId, WEEK)
        val current = RoundKey(nextTheme, nextWeek)

        // 다음 주 수요일: WEEK 회차만 지난 주
        val (frames, album) = servicesOn(nextWeek.plusDays(2))
        val page = album.album(student, 0, 20)
        assertEquals(listOf(past), page.items.map { RoundKey(it.themeId, it.weekStart) })
        assertEquals(1L, page.totalElements)
        assertEquals("물의 여행", page.items.single().title)
        assertFalse(page.items.single().seen)
        assertEquals(listOf(past), frames.owned(student, listOf(current, past, past, RoundKey(UUID.randomUUID(), WEEK))))
        assertNotFound { album.round(student, current) }
        assertNotFound { frames.markSeen(student, current) }
        // 그다음 주에는 둘 다 보이고 최근 회차가 먼저
        val (_, later) = servicesOn(nextWeek.plusWeeks(1))
        assertEquals(listOf(current, past), later.album(student, 0, 20).items.map { RoundKey(it.themeId, it.weekStart) })
        assertEquals(listOf(past), later.album(student, 1, 1).items.map { RoundKey(it.themeId, it.weekStart) })
        // 다른 학생 범위 밖
        assertEquals(0, album.album(UUID.randomUUID(), 0, 20).items.size)
    }

    @Test
    fun `새 액자 확인은 멱등이라 처음 시각을 유지하고, 미보유 회차는 404 THEME_FRAME_NOT_FOUND`() {
        val day = (0..4).map { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        frameService.awardIfComplete(load(day.last()))
        val key = RoundKey(themeId, WEEK)

        val (first, album) = servicesOn(WEEK.plusWeeks(1), hour = 9)
        first.markSeen(student, key)
        val seenAt = frames(student).single()["seen_at"]
        servicesOn(WEEK.plusWeeks(1), hour = 18).first.markSeen(student, key)

        assertNotNull(seenAt)
        assertEquals(seenAt, frames(student).single()["seen_at"])
        assertTrue(album.album(student, 0, 20).items.single().seen)
        assertNotFound { first.markSeen(UUID.randomUUID(), key) }
        assertNotFound { album.round(student, RoundKey(themeId, WEEK.minusWeeks(1))) }
    }

    @Test
    fun `회차 상세는 문제별 마지막 완료 시도를 주고, 엔딩(#484 ENDED) 전에는 종료 이야기·정답이 null`() {
        jdbc.update(
            "UPDATE weekly_theme_version SET outro = '물은 다시 하늘로', answer = '구름', intro_image_uri = 'theme-drafts/run/intro.png' WHERE id = ?",
            publishedVersion(),
        )
        val day = (0..4).map { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        val retry = attempt(missions[1], "THEME_REVIEW", completedAt = at(WEEK.plusDays(5)))
        attempt(missions[3], "THEME_REVIEW", startedAt = at(WEEK.plusDays(5))) // 진행 중 다시 풀기는 빼고
        frameService.awardIfComplete(load(day.last()))
        val key = RoundKey(themeId, WEEK)
        val (_, album) = servicesOn(WEEK.plusWeeks(1))

        val hidden = album.round(student, key)
        assertEquals("물의 여행", hidden.title)
        assertTrue(hidden.imageUrl!!.startsWith(TestAssets.BASE + "theme-drafts/run/intro.png"))
        assertEquals(ThemeDay.entries, hidden.missions.map { it.day })
        assertEquals(missions.map { it.id }, hidden.missions.map { it.missionId })
        assertEquals(listOf(day[0], retry, day[2], day[3], day[4]), hidden.missions.map { it.attemptId })
        assertFalse(hidden.ending.seen)
        assertNull(hidden.ending.outro)
        assertNull(hidden.ending.answer)
        // 이야기 열람 기록만으로는 엔딩이 아님(엔딩은 정답 고르기로 판정)
        storyView("INTRO")
        storyView("OUTRO")
        assertNull(album.round(student, key).ending.answer)

        // 금요일에 틀리게 고르면 금요일 문제 다시 풀기를 마무리하기 전까지 엔딩 전
        val pickedAt = at(WEEK.plusDays(4), 18).toInstant()
        themeRepository.recordAnswerPick(student, WEEK, themeId, missions[4].id, "비", false, pickedAt)
        assertFalse(album.round(student, key).ending.seen)

        val fridayRetry = attempt(missions[4], "THEME_REVIEW", completedAt = at(WEEK.plusDays(5), 11))
        clearMyBatisCache()
        val shown = album.round(student, key)
        assertTrue(shown.ending.seen)
        assertEquals("물은 다시 하늘로" to "구름", shown.ending.outro to shown.ending.answer)
        assertEquals(fridayRetry, shown.missions.last().attemptId)
    }

    @Test
    fun `회차 잠금은 같은 트랜잭션에서 다시 잡아도 막히지 않고 두 번째 판정은 0행`() {
        (0..4).forEach { attempt(missions[it], "THEME_DAY", completedAt = at(WEEK.plusDays(it.toLong()))) }
        val round = com.sagomungchi.learning.memory.repository.RoundFilter(student, themeId, WEEK)
        assertTrue(frameRepository.awardIfComplete(round, Instant.now()))
        assertFalse(frameRepository.awardIfComplete(round, Instant.now()))
    }

    private fun servicesOn(date: LocalDate, hour: Int = 12): Pair<ThemeFrameService, AlbumService> {
        val clock = Clock.fixed(date.atTime(hour, 0).atZone(KST).toInstant(), KST)
        val frames = ThemeFrameService(frameRepository, clock)
        return frames to AlbumService(frames, WeeklyThemeService(themeRepository, clock, TestAssets.urls), TestAssets.urls)
    }

    private fun assertNotFound(block: () -> Unit) {
        val error = assertThrows<RuntimeException> { block() }
        assertEquals(HttpStatus.NOT_FOUND to "THEME_FRAME_NOT_FOUND", httpStatusOf(error) to errorCodeOf(error))
    }

    /** MyBatis로 넣어야 같은 트랜잭션의 MyBatis 조회 캐시가 비워짐(실제 요청은 요청마다 트랜잭션) */
    private fun storyView(kind: String) = themeRepository.recordStoryView(student, WEEK, kind, themeId, Instant.now())

    /** JdbcTemplate으로 넣은 행을 같은 트랜잭션의 MyBatis 조회가 보게 함(MyBatis 쓰기는 세션 캐시를 비움) */
    private fun clearMyBatisCache() = themeRepository.recordReviewView(student, WEEK, themeId, Instant.now())

    private fun publishedVersion(): UUID =
        jdbc.queryForObject("SELECT published_version_id FROM weekly_theme WHERE id = ?", UUID::class.java, themeId)!!

    private fun frames(studentId: UUID): List<Map<String, Any?>> =
        jdbc.queryForList("SELECT * FROM theme_frame WHERE student_id = ? ORDER BY theme_week_start", studentId)

    private fun awardedAt(studentId: UUID): Instant =
        (frames(studentId).single()["awarded_at"] as java.sql.Timestamp).toInstant()

    private fun load(attemptId: UUID) = attemptRepository.findById(attemptId)!!

    private fun at(date: LocalDate, hour: Int = 10, minute: Int = 0): OffsetDateTime =
        date.atTime(hour, minute).atZone(KST).toOffsetDateTime()

    /** 시도 행 직접 삽입. completedAt이 있으면 학습 완료, finishedAt만 있으면 마무리 뒤 돌아보기 전 */
    private fun attempt(
        mission: TestRows.SeededMission,
        context: String,
        completedAt: OffsetDateTime? = null,
        finishedAt: OffsetDateTime? = completedAt,
        startedAt: OffsetDateTime = (finishedAt ?: completedAt ?: at(WEEK)).minusMinutes(30),
        theme: UUID? = themeId,
        week: LocalDate? = WEEK,
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

    private companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        /** 2026-11-02(월). 지금(테스트 실행일)보다 이른 주 */
        val WEEK: LocalDate = LocalDate.of(2026, 11, 2)
    }
}
