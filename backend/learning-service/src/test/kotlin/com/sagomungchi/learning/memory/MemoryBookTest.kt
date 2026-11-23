package com.sagomungchi.learning.memory

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.TestAssets
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.attempt.repository.AttemptRepository
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.repository.MemoryBookRepository
import com.sagomungchi.learning.memory.repository.ThemeFrameRepository
import com.sagomungchi.learning.memory.service.MemoryBookService
import com.sagomungchi.learning.memory.service.ThemeFrameService
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.repository.WeeklyThemeRepository
import com.sagomungchi.learning.theme.service.WeeklyThemeService
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

/**
 * 추억 그림책 회차 조립 (docs/proposals/memory-book.md 7.2, 미도입 시험 구현): 요일별 문제·장면·대화·답변(되묻기 순서)·돌아보기,
 * 장면은 시도가 쓴 미션 버전, 엔딩 전 종료 이야기·정답·종료 그림 비노출(P23), 미보유·남의 회차 404
 */
class MemoryBookTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var frameRepository: ThemeFrameRepository
    @Autowired lateinit var themeRepository: WeeklyThemeRepository
    @Autowired lateinit var attemptRepository: AttemptRepository
    @Autowired lateinit var json: ObjectMapper

    private lateinit var rows: TestRows
    private lateinit var missions: List<TestRows.SeededMission>
    private lateinit var themeId: UUID
    private lateinit var book: MemoryBookService
    private val student = UUID.randomUUID()

    @BeforeEach
    fun seed() {
        rows = TestRows(jdbc)
        missions = rows.themeMissions()
        themeId = rows.publishedTheme(missions.map { it.id }, WEEK, title = "등대 불빛", intro = "불빛이 꺼졌어요")
        jdbc.update(
            """UPDATE weekly_theme_version SET big_question = '왜 꺼졌을까?', outro = '빗장을 달았어요', answer = '바람',
                   intro_image_uri = 'theme-drafts/run/INTRO', outro_image_uri = 'theme-drafts/run/OUTRO' WHERE id = ?""",
            version(),
        )
        jdbc.update(
            """UPDATE weekly_theme_day SET dialogue = '[{"speaker":"등대지기","text":"바람이 셌단다"},{"speaker":"나비","text":"야옹"}]'::jsonb
               WHERE theme_version_id = ? AND day_of_week = 1""",
            version(),
        )
        missions.forEachIndexed { index, mission ->
            jdbc.update("UPDATE mission_version SET question = ?, scene_uri = ? WHERE id = ?",
                "문제 ${index + 1}", "theme-drafts/run/${ThemeDay.entries[index].name}", mission.versionId)
        }
        val clock = Clock.fixed(WEEK.plusWeeks(1).atTime(12, 0).atZone(KST).toInstant(), KST)
        book = MemoryBookService(
            ThemeFrameService(frameRepository, clock),
            WeeklyThemeService(themeRepository, clock, TestAssets.urls),
            MemoryBookRepository(jdbc, json),
            TestAssets.urls,
        )
    }

    @Test
    fun `요일 다섯 개에 문제·장면·대화·답변(되묻기 앞)·돌아보기, 엔딩 전이면 종료 이야기·정답·종료 그림 없음`() {
        val days = completeWeek()
        val first = answer(days[0], 1, "바람이 불었어요")
        answer(days[0], 2, "문이 열려서 꺼졌어요", followupOf = first, question = "언제 꺼졌을까?")
        jdbc.update("INSERT INTO reflection (id, attempt_id, difficulty, changed_text, created_at) VALUES (gen_random_uuid(), ?, 'NORMAL', '순서를 봤어요', now())", days[0])

        val round = book.round(student, RoundKey(themeId, WEEK))

        assertEquals("등대 불빛" to "불빛이 꺼졌어요", round.title to round.intro)
        assertEquals("왜 꺼졌을까?", round.bigQuestion)
        assertTrue(round.introImage!!.startsWith(TestAssets.BASE + "theme-drafts/run/INTRO"))
        assertEquals(ThemeDay.entries, round.days.map { it.day })
        assertEquals((1..5).map { "문제 $it" }, round.days.map { it.question })
        assertTrue(round.days[2].sceneImage!!.startsWith(TestAssets.BASE + "theme-drafts/run/WED"))
        assertEquals(listOf("등대지기" to "바람이 셌단다", "나비" to "야옹"), round.days[0].dialogue.map { it.speaker to it.text })
        assertEquals(emptyList(), round.days[1].dialogue)

        val monday = round.days[0].attempt!!
        assertEquals(days[0], monday.attemptId)
        assertEquals(listOf("바람이 불었어요", "문이 열려서 꺼졌어요"), monday.answers.map { it.text })
        assertNull(monday.answers[0].followup)
        assertEquals("TELL_MORE" to "언제 꺼졌을까?", monday.answers[1].followup!!.let { it.type to it.question })
        assertEquals("NORMAL" to "순서를 봤어요", monday.reflection!!.let { it.difficulty to it.text })
        assertNull(round.days[1].attempt!!.reflection)

        assertFalse(round.ending.seen)
        assertNull(round.ending.outro)
        assertNull(round.ending.answer)
        assertNull(round.ending.outroImage)
    }

    @Test
    fun `정답을 맞혀 엔딩을 본 회차는 종료 이야기·정답·종료 그림을 줌`() {
        completeWeek()
        themeRepository.recordAnswerPick(student, WEEK, themeId, missions[4].id, "바람", true, at(WEEK.plusDays(4), 18).toInstant())

        val ending = book.round(student, RoundKey(themeId, WEEK)).ending

        assertTrue(ending.seen)
        assertEquals("빗장을 달았어요" to "바람", ending.outro to ending.answer)
        assertTrue(ending.outroImage!!.startsWith(TestAssets.BASE + "theme-drafts/run/OUTRO"))
    }

    @Test
    fun `장면 그림·문제 글은 그 시도가 쓴 미션 버전 값(뒤에 미션이 고쳐져도 그때 그림)`() {
        completeWeek()
        val newer = rows.addVersion(missions[1].id, version = 2, title = "테마 2 수정")
        jdbc.update("UPDATE mission_version SET question = '고친 문제', scene_uri = 'theme-drafts/new/TUE' WHERE id = ?", newer)
        jdbc.update("UPDATE mission SET published_version_id = ?, current_version_id = ? WHERE id = ?", newer, newer, missions[1].id)

        val tuesday = book.round(student, RoundKey(themeId, WEEK)).days[1]

        assertEquals("문제 2", tuesday.question)
        assertTrue(tuesday.sceneImage!!.startsWith(TestAssets.BASE + "theme-drafts/run/TUE"))
    }

    @Test
    fun `미보유 회차와 다른 학생의 회차는 404 THEME_FRAME_NOT_FOUND`() {
        completeWeek()
        assertNotFound { book.round(student, RoundKey(themeId, WEEK.minusWeeks(1))) }
        assertNotFound { book.round(UUID.randomUUID(), RoundKey(themeId, WEEK)) }
    }

    /** 월~금 다섯 문제를 각 요일에 학습 완료하고 액자 지급. 시도 ID를 요일 순으로 */
    private fun completeWeek(): List<UUID> {
        val days = missions.mapIndexed { index, mission -> attempt(mission, at(WEEK.plusDays(index.toLong()))) }
        assertTrue(frameRepository.awardIfComplete(
            com.sagomungchi.learning.memory.repository.RoundFilter(student, themeId, WEEK), at(WEEK.plusDays(4)).toInstant(),
        ))
        assertTrue(attemptRepository.findById(days.last()) != null)
        return days
    }

    private fun attempt(mission: TestRows.SeededMission, completedAt: OffsetDateTime): UUID = UUID.randomUUID().also {
        jdbc.update(
            """INSERT INTO attempt (id, student_id, mission_id, mission_version_id, rubric_version_id, grade, status,
                   started_at, finished_at, completed_at, updated_at, context, theme_id, theme_week_start, theme_version_id)
               VALUES (?, ?, ?, ?, ?, 3, 'COMPLETED', ?, ?, ?, ?, 'THEME_DAY', ?, ?, ?)""",
            it, student, mission.id, mission.versionId, mission.rubricVersionId, completedAt.minusMinutes(30), completedAt, completedAt,
            completedAt, themeId, WEEK, version(),
        )
    }

    /** 답변 1개. followupOf가 있으면 그 답변의 판정에서 나온 되묻기에 대한 보완 답변 */
    private fun answer(attemptId: UUID, version: Int, text: String, followupOf: UUID? = null, question: String? = null): UUID {
        val followupId = followupOf?.let { previous ->
            val judgment = UUID.randomUUID()
            val rubric = jdbc.queryForObject("SELECT rubric_version_id FROM attempt WHERE id = ?", UUID::class.java, attemptId)
            jdbc.update(
                """INSERT INTO judgment (id, answer_id, process_status, result, method, rubric_version_id, retry_count, created_at)
                   VALUES (?, ?, 'DONE', 'RETHINK', 'LLM', ?, 0, now())""",
                judgment, previous, rubric,
            )
            UUID.randomUUID().also { id ->
                jdbc.update(
                    """INSERT INTO followup (id, attempt_id, judgment_id, type, question, source, leak_check_passed, created_at)
                       VALUES (?, ?, ?, 'TELL_MORE', ?, 'LLM', true, now())""",
                    id, attemptId, judgment, question,
                )
            }
        }
        return UUID.randomUUID().also {
            jdbc.update(
                """INSERT INTO answer (id, attempt_id, version, followup_id, input_type, content, plain_text, dictated_by_guardian, idempotency_key, submitted_at)
                   VALUES (?, ?, ?, ?, 'NARRATIVE', '{}'::jsonb, ?, false, ?, now())""",
                it, attemptId, version, followupId, text, UUID.randomUUID(),
            )
        }
    }

    private fun assertNotFound(block: () -> Unit) {
        val error = assertThrows<RuntimeException> { block() }
        assertEquals(HttpStatus.NOT_FOUND to "THEME_FRAME_NOT_FOUND", httpStatusOf(error) to errorCodeOf(error))
    }

    private fun version(): UUID =
        jdbc.queryForObject("SELECT published_version_id FROM weekly_theme WHERE id = ?", UUID::class.java, themeId)!!

    private fun at(date: LocalDate, hour: Int = 10): OffsetDateTime = date.atTime(hour, 0).atZone(KST).toOffsetDateTime()

    private companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        /** 2026-11-02(월). 지금(테스트 실행일)보다 이른 주 */
        val WEEK: LocalDate = LocalDate.of(2026, 11, 2)
    }
}
