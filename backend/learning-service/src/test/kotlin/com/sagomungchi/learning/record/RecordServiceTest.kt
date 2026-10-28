package com.sagomungchi.learning.record

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.Answer
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.Essay
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.record.domain.QueryState
import com.sagomungchi.learning.record.domain.TextCounts
import com.sagomungchi.learning.record.service.RecordService
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 이슈 #27 기록 조회: 집계 기준 P08, 상태(0건·1~4건·5건 이상), 전후 변화, 근거, 운영 집계 */
class RecordServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: RecordService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var jdbc: JdbcTemplate

    private lateinit var rows: TestRows
    private val student = UUID.randomUUID()
    private val week = Period(LocalDate.parse("2026-11-02"), LocalDate.parse("2026-11-08"))
    private val inWeek = OffsetDateTime.parse("2026-11-03T10:00:00+09:00")

    @BeforeEach
    fun prepare() {
        rows = TestRows(jdbc)
        actAs(student)
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    private fun actAs(vararg students: UUID, role: String = "PARENT") =
        UserContextHolder.set(UserContext(null, role, students.map { it.toString() }.toSet(), null))

    /** 미션 하나에 시도 하나 (진행 중 시도는 미션마다 하나라 미션을 새로 만듦) */
    private fun attempt(type: ThinkingType = ThinkingType.ANALYZE, title: String = "미션", owner: UUID = student): Attempt {
        val mission = rows.mission(title = title)
        rows.rubric(mission)
        jdbc.update("UPDATE mission_version SET thinking_type = ? WHERE id = ?", type.name, mission.versionId)
        val previous = UserContextHolder.current()
        actAs(owner, role = "STUDENT")
        try {
            return attemptService.start(owner, mission.id, 3, demo = false).attempt
        } finally {
            UserContextHolder.set(previous)
        }
    }

    private fun answer(attempt: Attempt, text: String, at: OffsetDateTime = inWeek, followupId: UUID? = null): Answer {
        val previous = UserContextHolder.current()
        actAs(attempt.studentId, role = "STUDENT")
        try {
            return answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = text), false, followupId))
                .also { jdbc.update("UPDATE answer SET submitted_at = ? WHERE id = ?", at, it.id) }
        } finally {
            UserContextHolder.set(previous)
        }
    }

    /** 되묻기를 받고 보완 답변 */
    private fun revise(attempt: Attempt, first: Answer, text: String, at: OffsetDateTime = inWeek.plusMinutes(5)): Answer =
        answer(attempt, text, at, rows.followup(attempt.id, first.id))

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit) {
        val error = assertThrows<BusinessException> { block() }
        assertEquals(status to code, error.status to error.code)
    }

    @Test
    fun `기록이 0건이면 NO_RECORD, 1~4건이면 표본 부족으로 비율 대신 개수만, 5건 이상이면 OK와 비율 (P08)`() {
        assertEquals(QueryState.NO_RECORD, service.summary(student, week).state)

        val attempts = (1..5).map { attempt(title = "미션 $it") }
        attempts.take(4).forEach { answer(it, "놀 수 있어서 좋아요") }
        val small = service.summary(student, week)
        assertEquals(QueryState.INSUFFICIENT_SAMPLE, small.state)
        val completedSmall = small.metrics.single { it.label == "완료한 활동" }
        assertEquals(listOf(0, 4, null), listOf(completedSmall.numerator, completedSmall.denominator, completedSmall.value))

        answer(attempts[4], "놀 수 있어서 좋아요")
        jdbc.update("UPDATE attempt SET status = 'COMPLETED', finished_at = now(), completed_at = now() WHERE id = ?", attempts[0].id)
        val full = service.summary(student, week)
        assertEquals(QueryState.OK, full.state)
        val count = full.metrics.single { it.label == "학습한 활동" }
        assertEquals(listOf(5, 5, null), listOf(count.count, count.denominator, count.value))
        assertEquals(0.2, full.metrics.single { it.label == "완료한 활동" }.value)
    }

    @Test
    fun `집계 대상은 기간 안에 처리 실패가 아닌 답변을 낸 시도만, 미완료 포함 (P08)`() {
        answer(attempt(title = "기간 안"), "기간 안 답변")
        answer(attempt(title = "기간 밖"), "지난주 답변", inWeek.minusDays(7))
        attempt(title = "초안만")
        val failed = answer(attempt(title = "실패만"), "실패한 답변")
        jdbc.update("UPDATE judgment SET process_status = 'FAILED', failure_code = 'AI_TIMEOUT', retry_count = 1 WHERE answer_id = ?", failed.id)

        val listed = service.attempts(student, week, 0, 20)

        assertEquals(listOf("기간 안"), listed.items.map { it.mission.title })
        assertEquals(1 to QueryState.INSUFFICIENT_SAMPLE, listed.totalElements to listed.state)
    }

    @Test
    fun `기간은 KST 날짜 양 끝 포함, 끝 날짜 23시 59분은 들어가고 다음 날 0시는 빠짐`() {
        answer(attempt(title = "일요일 밤"), "답", OffsetDateTime.parse("2026-11-08T23:59:00+09:00"))
        answer(attempt(title = "월요일 0시"), "답", OffsetDateTime.parse("2026-11-09T00:00:00+09:00"))
        answer(attempt(title = "월요일 시작"), "답", OffsetDateTime.parse("2026-11-02T00:00:00+09:00"))

        assertEquals(setOf("일요일 밤", "월요일 시작"), service.attempts(student, week, 0, 20).items.map { it.mission.title }.toSet())
    }

    @Test
    fun `도움 없이 시작은 최초 답변 전 생각 열기, 생각을 더한 활동은 되묻기 받은 시도 중 보완 답변 낸 시도`() {
        val helpedFirst = attempt(title = "먼저 도움")
        val first = answer(helpedFirst, "처음 답")
        jdbc.update("INSERT INTO hint_usage (id, attempt_id, hint_question_id, opened_at) SELECT gen_random_uuid(), ?, id, ? FROM hint_question WHERE rubric_version_id = ? LIMIT 1",
            helpedFirst.id, inWeek.minusMinutes(1), helpedFirst.rubricVersionId)
        revise(helpedFirst, first, "보완 답")
        val helpedLater = attempt(title = "나중에 도움")
        val later = answer(helpedLater, "처음 답")
        rows.followup(helpedLater.id, later.id)
        jdbc.update("INSERT INTO hint_usage (id, attempt_id, hint_question_id, opened_at) SELECT gen_random_uuid(), ?, id, ? FROM hint_question WHERE rubric_version_id = ? LIMIT 1",
            helpedLater.id, inWeek.plusMinutes(1), helpedLater.rubricVersionId)
        answer(attempt(title = "되묻기 없음"), "처음 답")

        val metrics = service.summary(student, week).metrics.associateBy { it.label }

        val noHelp = metrics.getValue("도움 없이 시작한 활동")
        assertEquals(2 to 3, noHelp.numerator to noHelp.denominator)
        val revised = metrics.getValue("되묻기 후 생각을 더한 활동")
        assertEquals(1 to 2, revised.numerator to revised.denominator)
        assertNull(revised.value)
    }

    @Test
    fun `유형별 활동은 다섯 유형 모두, 기록이 없는 유형은 NO_RECORD`() {
        answer(attempt(ThinkingType.ANALYZE, "원인 찾기"), "답")
        answer(attempt(ThinkingType.CREATE, "새로 만들기"), "답")

        val types = service.thinkingTypes(student, week)

        assertEquals(ThinkingType.entries, types.items.map { it.type })
        assertEquals(listOf("원인 찾기"), types.items.single { it.type == ThinkingType.ANALYZE }.missions.map { it.title })
        assertEquals(
            mapOf(ThinkingType.ANALYZE to QueryState.OK, ThinkingType.EVALUATE to QueryState.NO_RECORD, ThinkingType.CREATE to QueryState.OK,
                ThinkingType.SOLVE to QueryState.NO_RECORD, ThinkingType.REFLECT to QueryState.NO_RECORD),
            types.items.associate { it.type to it.state },
        )
    }

    @Test
    fun `기록 목록은 최근 답변 순으로 나눠 주고 상세는 이 학생의 기록된 시도만 (다른 학생·실패만 404)`() {
        val older = attempt(title = "먼저")
        answer(older, "답", inWeek)
        val newer = attempt(title = "나중")
        answer(newer, "답", inWeek.plusDays(1))

        val first = service.attempts(student, week, 0, 1)
        assertEquals(listOf("나중") to 2, first.items.map { it.mission.title } to first.totalElements)
        assertEquals(listOf("먼저"), service.attempts(student, week, 1, 1).items.map { it.mission.title })
        assertEquals(newer.id, service.attempt(student, newer.id).attempt.id)

        val other = UUID.randomUUID()
        val othersAttempt = attempt(title = "다른 학생", owner = other)
        answer(othersAttempt, "답")
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { service.attempt(student, othersAttempt.id) }
        val failed = attempt(title = "실패만")
        val failedAnswer = answer(failed, "답")
        jdbc.update("UPDATE judgment SET process_status = 'FAILED', failure_code = 'AI_TIMEOUT', retry_count = 1 WHERE answer_id = ?", failedAnswer.id)
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { service.attempt(student, failed.id) }
    }

    @Test
    fun `전후 변화는 보완 답변이 있는 시도의 최초 vs 마지막 답변, 마지막 답변이 답한 되묻기와 학생이 쓴 칸의 수`() {
        val attempt = attempt(title = "쉬는 시간")
        val first = answer(attempt, "좋아요")
        val second = revise(attempt, first, "더 놀 수 있어요")
        val last = answer(attempt, "왜냐하면 친구랑 놀 수 있기 때문이에요. 그래서 좋아요!", inWeek.plusMinutes(10), rows.followup(attempt.id, second.id, minutesLater = 2))
        answer(attempt(title = "보완 없음"), "한 번만")

        val change = service.changes(student, week).items.single()

        assertEquals(first.id to last.id, change.pair.firstAnswerId to change.pair.lastAnswerId)
        assertEquals("좋아요" to "왜냐하면 친구랑 놀 수 있기 때문이에요. 그래서 좋아요!", change.pair.firstText to change.pair.lastText)
        assertEquals("왜 그렇게 생각했나요?", change.pair.followup)
        assertEquals(TextCounts(3, 1, 0), change.first)
        assertEquals(TextCounts(31, 2, 3), change.revised)
    }

    @Test
    fun `전후 변화의 원문은 칸 이름을 붙인 그대로 주고, 수는 칸 이름(물음표 포함)을 빼고 학생이 쓴 칸만 셈`() {
        val mission = rows.mission(inputType = "SOLUTION_STEPS", inputTemplate = """["① 무엇을 구하나요?"]""")
        rows.rubric(mission, answerKey = """{"finalAnswer": "420원"}""")
        actAs(student, role = "STUDENT")
        val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
        fun steps(step: String, followupId: UUID?) =
            answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.SOLUTION_STEPS, AnswerContent(steps = listOf(step), finalAnswer = "420원"), false, followupId))
                .also { jdbc.update("UPDATE answer SET submitted_at = ? WHERE id = ?", inWeek, it.id) }
        val first = steps("남은 돈", null)
        steps("900원에서 480원을 빼요", rows.followup(attempt.id, first.id))
        actAs(student)

        val change = service.changes(student, week).items.single()

        assertEquals("① 무엇을 구하나요?: 900원에서 480원을 빼요\n최종 답: 420원", change.pair.lastText)
        assertEquals(TextCounts.of("900원에서 480원을 빼요\n420원"), change.revised)
        assertEquals(2, change.revised.sentences)
    }

    @Test
    fun `학생이 쓴 칸만 셈 - 논술은 네 칸, 칸 이름은 세지 않음`() {
        val essay = AnswerContent(essay = Essay("늘려야 해요.", listOf("놀 수 있어요.", "쉬어야 해요."), "공부도 해요."))
        assertEquals("늘려야 해요.\n놀 수 있어요.\n쉬어야 해요.\n공부도 해요.", TextCounts.writtenText(essay))
        assertEquals(4, TextCounts.of(essay).sentences)
        assertEquals("", TextCounts.writtenText(AnswerContent(choiceIds = listOf("c1"))))
    }

    @Test
    fun `근거는 요청 순서대로 원문을 주고 없는 답변·삭제 학생은 원문 없이 available false, 범위 밖 학생은 403`() {
        val mine = answer(attempt(title = "내 미션"), "내가 쓴 생각")
        val missing = UUID.randomUUID()

        val evidence = service.evidence(listOf(missing, mine.id))

        assertEquals(listOf(missing, mine.id), evidence.map { it.answerId })
        assertEquals(listOf(false, true), evidence.map { it.available })
        assertEquals(listOf(null, "내가 쓴 생각"), evidence.map { it.quote })
        assertEquals("내 미션", evidence[1].missionTitle)

        val other = UUID.randomUUID()
        val others = answer(attempt(title = "다른 학생", owner = other), "남의 생각")
        assertError(HttpStatus.FORBIDDEN, "FORBIDDEN") { service.evidence(listOf(mine.id, others.id)) }

        jdbc.update("INSERT INTO deleted_student (student_id, scope, event_id, deleted_at) VALUES (?, 'RECORDS', ?, now())", student, UUID.randomUUID())
        val afterDeletion = service.evidence(listOf(mine.id)).single()
        assertFalse(afterDeletion.available)
        assertNull(afterDeletion.quote)
        assertEquals(QueryState.NO_RECORD, service.summary(student, week).state)
    }

    @Test
    fun `운영 집계는 학생 원문 없이 기간 내 집계 대상 시도·완료·학생 수`() {
        val before = service.stats(week)
        val done = attempt(title = "완료")
        answer(done, "답")
        jdbc.update("UPDATE attempt SET status = 'COMPLETED', finished_at = now(), completed_at = now() WHERE id = ?", done.id)
        answer(attempt(title = "진행 중"), "답")
        val other = UUID.randomUUID()
        answer(attempt(title = "다른 학생", owner = other), "답")

        val after = service.stats(week)

        assertEquals(
            listOf(before.attempts + 3, before.completedAttempts + 1, before.students + 2),
            listOf(after.attempts, after.completedAttempts, after.students),
        )
        assertTrue(after.attempts >= 3)
    }
}
