package com.sagomungchi.learning.answer.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.Assignment
import com.sagomungchi.learning.answer.domain.Essay
import com.sagomungchi.learning.answer.repository.AnswerRepository
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.attempt.service.DraftConflictException
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.mybatis.spring.SqlSessionTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull

class AnswerServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var sqlSession: SqlSessionTemplate
    @Autowired lateinit var answerRepository: AnswerRepository

    private lateinit var rows: TestRows
    private val student = UUID.randomUUID()

    @BeforeEach
    fun prepare() {
        rows = TestRows(jdbc)
        actAs(student)
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    private fun actAs(studentId: UUID) =
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(studentId.toString()), null))

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit): BusinessException {
        val error = assertThrows<BusinessException> { block() }
        assertEquals(status to code, error.status to error.code)
        return error
    }

    private fun start(inputType: String = "NARRATIVE", grade: Int = 3): Attempt =
        attemptService.start(student, rows.mission(inputType = inputType, grade = grade).id, grade, demo = false).attempt

    /**
     * 되묻기는 #25가 만들어서 JdbcTemplate으로 직접 넣음. 테스트는 한 트랜잭션이라
     * MyBatis가 기억한 이전 조회 결과(되묻기 없음)를 비워 줌
     */
    private fun followup(attemptId: UUID, answerId: UUID, minutesLater: Long = 1) =
        rows.followup(attemptId, answerId, minutesLater).also { sqlSession.clearCache() }

    private fun narrative(text: String, followupId: UUID? = null) =
        SubmitCommand(InputType.NARRATIVE, AnswerContent(text = text), dictatedByGuardian = false, followupId = followupId)

    private fun count(sql: String, id: UUID) = jdbc.queryForObject(sql, Int::class.java, id)

    @Test
    fun `첫 답변은 버전 1, 판정 PENDING을 시도의 기준표 버전으로 만들고 시도 상세에 보임`() {
        val attempt = start()

        val answer = service.submit(attempt.id, UUID.randomUUID(), narrative("물이 얼면 부피가 커져요"))

        assertEquals(1, answer.version)
        assertNull(answer.previousAnswerId)
        assertEquals("물이 얼면 부피가 커져요", answer.plainText)
        val judgment = jdbc.queryForMap("SELECT process_status, rubric_version_id, retry_count FROM judgment WHERE answer_id = ?", answer.id)
        assertEquals(listOf("PENDING", attempt.rubricVersionId, 0), listOf(judgment["process_status"], judgment["rubric_version_id"], judgment["retry_count"]))
        val timeline = attemptService.get(attempt.id).answers.single()
        assertEquals(
            listOf(answer.id, 1, "물이 얼면 부피가 커져요", mapOf("text" to "물이 얼면 부피가 커져요"), ProcessStatus.PENDING),
            listOf(timeline.answerId, timeline.version, timeline.text, timeline.content, timeline.processStatus),
        )
    }

    @Test
    fun `제출하면 초안은 답 칸만 비우고 메모 유지·버전 +1, 같은 키 재요청은 다시 비우지 않음`() {
        val attempt = start()
        attemptService.saveDraft(attempt.id, ifMatch = 0, content = DraftContent(mapOf("text" to "쓰던 답"), "메모"))
        val key = UUID.randomUUID()

        val answer = service.submit(attempt.id, key, narrative("쓰던 답"))
        service.submit(attempt.id, key, narrative("쓰던 답"))

        val draft = attemptService.get(attempt.id).draft
        assertEquals(Triple(2, DraftContent(emptyMap(), "메모"), answer.submittedAt), Triple(draft.version, draft.content, draft.savedAt))
        assertThrows<DraftConflictException> {
            attemptService.saveDraft(attempt.id, ifMatch = 1, content = DraftContent(mapOf("text" to "다른 화면"), "메모"))
        }
    }

    @Test
    fun `저장하지 못한 제출은 초안을 그대로 둠`() {
        val attempt = start()
        val saved = attemptService.saveDraft(attempt.id, ifMatch = 0, content = DraftContent(mapOf("text" to " "), "메모"))

        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") { service.submit(attempt.id, UUID.randomUUID(), narrative(" ")) }

        assertEquals(saved, attemptService.get(attempt.id).draft)
    }

    @Test
    fun `입력 방식에 안 쓰는 필드는 저장하지 않음`() {
        val attempt = start("ESSAY", grade = 5)
        val command = SubmitCommand(
            InputType.ESSAY,
            AnswerContent(text = "남은 글", essay = Essay("찬성", listOf("안전", "편리"), "그래도 필요")),
            dictatedByGuardian = true, followupId = null,
        )

        val answer = service.submit(attempt.id, UUID.randomUUID(), command)

        assertEquals(AnswerContent(essay = Essay("찬성", listOf("안전", "편리"), "그래도 필요")), answer.content)
        val stored = jdbc.queryForMap("SELECT content::text AS content, dictated_by_guardian FROM answer WHERE id = ?", answer.id)
        assertEquals("""{"essay": {"claim": "찬성", "reasons": ["안전", "편리"], "rebuttal": "그래도 필요"}}""", stored["content"])
        assertEquals(true, stored["dictated_by_guardian"])
    }

    @Test
    fun `같은 키 재요청은 처음 답변을 그대로, 다른 본문이면 422 IDEMPOTENCY_KEY_REUSED`() {
        val attempt = start()
        val key = UUID.randomUUID()

        val first = service.submit(attempt.id, key, narrative("처음"))
        val again = service.submit(attempt.id, key, narrative("처음"))
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "IDEMPOTENCY_KEY_REUSED") { service.submit(attempt.id, key, narrative("바꿈")) }

        assertEquals(first, again)
        assertEquals(1, count("SELECT count(*) FROM answer WHERE attempt_id = ?", attempt.id))
        assertEquals(1, count("SELECT count(*) FROM judgment WHERE answer_id = ?", first.id))
    }

    @Test
    fun `입력 방식마다 저장한 내용을 다시 읽어도 같은 키 재요청은 같은 답변`() {
        val choices = """[{"id": "a", "label": "물"}, {"id": "b", "label": "얼음"}]"""
        val commands = mapOf(
            ("CHOICE" to 3) to SubmitCommand(InputType.CHOICE, AnswerContent(choiceIds = listOf("b")), false, null),
            ("ORDERING" to 3) to SubmitCommand(InputType.ORDERING, AnswerContent(choiceIds = listOf("b", "a")), false, null),
            ("CLASSIFICATION" to 3) to SubmitCommand(
                InputType.CLASSIFICATION, AnswerContent(assignments = listOf(Assignment("a", "액체"), Assignment("b", "고체"))), false, null,
            ),
            ("SOLUTION_STEPS" to 3) to SubmitCommand(InputType.SOLUTION_STEPS, AnswerContent(finalAnswer = "6", steps = listOf("2씩 3묶음", "")), true, null),
            ("ESSAY" to 5) to SubmitCommand(InputType.ESSAY, AnswerContent(essay = Essay("찬성", listOf("안전", "편리"), "그래도 필요")), false, null),
        )
        commands.forEach { (type, command) ->
            val mission = rows.mission(inputType = type.first, grade = type.second, choices = choices)
            val attempt = attemptService.start(student, mission.id, type.second, demo = false).attempt
            val key = UUID.randomUUID()

            val first = service.submit(attempt.id, key, command)

            assertEquals(first, service.submit(attempt.id, key, command), type.first)
            assertEquals(command.content, answerRepository.findLatest(attempt.id)?.content, type.first)
        }
    }

    @Test
    fun `보완 답변은 가장 최근 되묻기에 연결해야 버전 2, 이전 답변에 이어짐`() {
        val attempt = start()
        val first = service.submit(attempt.id, UUID.randomUUID(), narrative("처음"))
        val noFollowup = assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("판정 전 추가"))
        }
        assertEquals("지금은 답할 추가 질문이 없어요.", noFollowup.detail)

        val followup = followup(attempt.id, first.id)
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") { service.submit(attempt.id, UUID.randomUUID(), narrative("연결 없음")) }
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("다른 질문", followupId = UUID.randomUUID()))
        }
        val second = service.submit(attempt.id, UUID.randomUUID(), narrative("보완", followupId = followup))

        assertEquals(Triple(2, first.id, followup), Triple(second.version, second.previousAnswerId, second.followupId))
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("같은 질문에 또", followupId = followup))
        }
        assertEquals(listOf(1, 2), attemptService.get(attempt.id).answers.map { it.version })
    }

    @Test
    fun `되묻기가 새로 생기면 지난 되묻기에는 연결할 수 없음`() {
        val attempt = start()
        val first = service.submit(attempt.id, UUID.randomUUID(), narrative("처음"))
        val old = followup(attempt.id, first.id, minutesLater = 1)
        val second = service.submit(attempt.id, UUID.randomUUID(), narrative("보완", followupId = old))
        val latest = followup(attempt.id, second.id, minutesLater = 2)

        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("지난 질문", followupId = old))
        }
        assertEquals(3, service.submit(attempt.id, UUID.randomUUID(), narrative("최근 질문", followupId = latest)).version)
    }

    @Test
    fun `첫 답변에 되묻기를 붙이거나 입력 방식이 다르거나 빈칸이면 저장하지 않음`() {
        val attempt = start()

        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("처음", followupId = UUID.randomUUID()))
        }
        assertError(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED") {
            service.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.CHOICE, AnswerContent(choiceIds = listOf("a")), false, null))
        }
        val blank = assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative(" "))
        }

        assertEquals("내 생각을 먼저 적어 주세요.", blank.detail)
        assertEquals(0, count("SELECT count(*) FROM answer WHERE attempt_id = ?", attempt.id))
    }

    @Test
    fun `마무리했거나 완료된 시도는 409, 이미 보낸 키의 재요청은 그대로`() {
        val finished = start()
        val key = UUID.randomUUID()
        val sent = service.submit(finished.id, key, narrative("처음"))
        jdbc.update("UPDATE attempt SET finished_at = now() WHERE id = ?", finished.id)

        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.submit(finished.id, UUID.randomUUID(), narrative("마무리 뒤")) }
        assertEquals(sent, service.submit(finished.id, key, narrative("처음")))

        val completed = attemptService.start(student, rows.mission().id, 3, false).attempt
        jdbc.update("UPDATE attempt SET status = 'COMPLETED' WHERE id = ?", completed.id)
        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.submit(completed.id, UUID.randomUUID(), narrative("완료 뒤")) }
    }

    @Test
    fun `다른 학생의 시도는 403, 없는 시도는 404`() {
        val attempt = start()

        actAs(UUID.randomUUID())
        assertError(HttpStatus.FORBIDDEN, "FORBIDDEN") { service.submit(attempt.id, UUID.randomUUID(), narrative("남의 답")) }
        assertError(HttpStatus.NOT_FOUND, "NOT_FOUND") { service.submit(UUID.randomUUID(), UUID.randomUUID(), narrative("없음")) }
    }
}
