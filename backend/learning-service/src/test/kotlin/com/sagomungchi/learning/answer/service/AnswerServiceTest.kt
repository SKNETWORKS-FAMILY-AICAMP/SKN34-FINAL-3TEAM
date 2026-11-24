package com.sagomungchi.learning.answer.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.exception.ErrorInfo
import com.sagomungchi.learning._common.exception.GlobalExceptionHandler
import com.sagomungchi.learning._common.exception.errorInfoOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.client.ToxicityClient
import com.sagomungchi.learning.answer.client.ToxicitySkipReason
import com.sagomungchi.learning.answer.client.ToxicityVerdict
import com.sagomungchi.learning.answer.domain.Answer
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
import org.junit.jupiter.api.extension.ExtendWith
import org.mockito.ArgumentMatchers.anyList
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verify
import org.mybatis.spring.SqlSessionTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.system.CapturedOutput
import org.springframework.boot.test.system.OutputCaptureExtension
import org.springframework.dao.DataIntegrityViolationException
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.mock.web.MockHttpServletRequest
import org.springframework.test.context.bean.override.mockito.MockitoBean
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

@ExtendWith(OutputCaptureExtension::class)
class AnswerServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var sqlSession: SqlSessionTemplate
    @Autowired lateinit var answerRepository: AnswerRepository

    /** scoring 표현 분류 (#692). 기본은 통과, 시험마다 결과를 바꿈. HTTP 계약은 ToxicityClientTest */
    @MockitoBean lateinit var toxicity: ToxicityClient

    private lateinit var rows: TestRows
    private val student = UUID.randomUUID()

    @BeforeEach
    fun prepare() {
        rows = TestRows(jdbc)
        actAs(student)
        modelSays(ToxicityVerdict.Clean(review = false))
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    private fun actAs(studentId: UUID) =
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(studentId.toString()), null))

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit): ErrorInfo {
        val error = checkNotNull(errorInfoOf(assertThrows<RuntimeException> { block() }))
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

    private fun modelSays(verdict: ToxicityVerdict) = given(toxicity.check(anyList())).willReturn(verdict)

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
    fun `욕설·연락처가 있는 답변은 저장·판정 없이 422 ANSWER_INAPPROPRIATE와 범주별 안내, 초안은 그대로`(output: CapturedOutput) {
        val attempt = start()
        val saved = attemptService.saveDraft(attempt.id, ifMatch = 0, content = DraftContent(mapOf("text" to "쓰던 답"), "메모"))

        val profanity = assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("이 문제 존나 어렵다"))
        }
        val contact = assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("내 번호는 010-1234-5678"))
        }

        assertEquals("고쳐야 할 말이 있어요" to "고운 말로 바꿔서 다시 적어 주세요.", profanity.title to profanity.detail)
        assertEquals("전화번호나 이메일 같은 개인정보는 빼고 다시 적어 주세요.", contact.detail)
        assertEquals(0, count("SELECT count(*) FROM answer WHERE attempt_id = ?", attempt.id))
        assertEquals(saved, attemptService.get(attempt.id).draft)
        assertTrue("attemptId=${attempt.id} category=PROFANITY" in output.out)
        assertFalse("존나" in output.out || "1234-5678" in output.out)
    }

    @Test
    fun `보완 답변도 같은 검사, 되묻기 연결 검사보다 먼저이고 판정을 만들지 않음`() {
        val attempt = start()
        val first = service.submit(attempt.id, UUID.randomUUID(), narrative("처음"))

        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") { service.submit(attempt.id, UUID.randomUUID(), narrative("씨발")) }
        val followup = followup(attempt.id, first.id)
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("자살해라", followupId = followup))
        }

        assertEquals(listOf(1), attemptService.get(attempt.id).answers.map { it.version })
        assertEquals(1, count("SELECT count(*) FROM judgment j JOIN answer a ON a.id = j.answer_id WHERE a.attempt_id = ?", attempt.id))
        assertEquals(2, service.submit(attempt.id, UUID.randomUUID(), narrative("고운 말로 고친 보완", followupId = followup)).version)
    }

    @Test
    fun `단어 목록을 통과해도 분류 모델이 걸면 저장·판정 없이 같은 422와 안내, 로그에는 INSULT만`(output: CapturedOutput) {
        val attempt = start()
        val saved = attemptService.saveDraft(attempt.id, ifMatch = 0, content = DraftContent(mapOf("text" to "쓰던 답"), "메모"))
        modelSays(ToxicityVerdict.Flagged)

        val error = assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("너는 머리가 텅 비었구나"))
        }

        assertEquals("고쳐야 할 말이 있어요" to "고운 말로 바꿔서 다시 적어 주세요.", error.title to error.detail)
        assertEquals(0, count("SELECT count(*) FROM answer WHERE attempt_id = ?", attempt.id))
        assertEquals(0, count("SELECT count(*) FROM judgment j JOIN answer a ON a.id = j.answer_id WHERE a.attempt_id = ?", attempt.id))
        assertEquals(saved, attemptService.get(attempt.id).draft)
        assertTrue("attemptId=${attempt.id} category=INSULT" in output.out)
        assertFalse("텅 비었" in output.out)
        verify(toxicity).check(listOf("너는 머리가 텅 비었구나"))
    }

    @Test
    fun `분류 모델이 검사하지 못하면 막지 않고 저장, 로그에는 사유만`(output: CapturedOutput) {
        for (reason in ToxicitySkipReason.entries) {
            val attempt = start()
            modelSays(ToxicityVerdict.Skipped(reason))

            val answer = service.submit(attempt.id, UUID.randomUUID(), narrative("모델이 쉬는 동안 낸 답"))

            assertEquals(1, answer.version)
            val logged = "답변 표현 분류 건너뜀 attemptId=${attempt.id} reason=$reason" in output.out
            assertEquals(reason != ToxicitySkipReason.DISABLED, logged, reason.name)
        }
        assertFalse("모델이 쉬는 동안" in output.out)
    }

    @Test
    fun `보완 답변도 분류 모델이 걸면 422, 단어 목록에 먼저 걸리면 그 범주`(output: CapturedOutput) {
        val attempt = start()
        val first = service.submit(attempt.id, UUID.randomUUID(), narrative("처음"))
        val followup = followup(attempt.id, first.id)
        modelSays(ToxicityVerdict.Flagged)

        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("비꼬는 보완", followupId = followup))
        }
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") {
            service.submit(attempt.id, UUID.randomUUID(), narrative("씨발", followupId = followup))
        }

        assertEquals(listOf(1), attemptService.get(attempt.id).answers.map { it.version })
        assertTrue("attemptId=${attempt.id} category=INSULT" in output.out)
        assertTrue("attemptId=${attempt.id} category=PROFANITY" in output.out)
        modelSays(ToxicityVerdict.Clean(review = true))
        assertEquals(2, service.submit(attempt.id, UUID.randomUUID(), narrative("고운 말로 고친 보완", followupId = followup)).version)
    }

    @Test
    fun `경계 구간 review이고 저장된 답변만 표현 검토 대기에 한 번 올림, 로그에 ID 없음`(output: CapturedOutput) {
        val model = "tox-koelectra-small:1.0-1119"
        val reviewsOf = { attemptId: UUID ->
            count("SELECT count(*) FROM expression_review r JOIN answer a ON a.id = r.answer_id WHERE a.attempt_id = ?", attemptId)
        }
        val gray = start()
        val key = UUID.randomUUID()
        modelSays(ToxicityVerdict.Clean(review = true, modelVersion = model))

        val answer = service.submit(gray.id, key, narrative("애매한 합성 답"))
        service.submit(gray.id, key, narrative("애매한 합성 답"))

        val row = jdbc.queryForMap(
            "SELECT source, model_version, label, labeled_by, labeled_at FROM expression_review WHERE answer_id = ?", answer.id,
        )
        assertEquals(
            listOf<Any?>("GRAY_ZONE", model, null, null, null),
            listOf(row["source"], row["model_version"], row["label"], row["labeled_by"], row["labeled_at"]),
        )
        assertEquals(1, reviewsOf(gray.id))
        val logLines = output.out.lines().filter { "표현 검토 대기 추가" in it }
        assertEquals(1, logLines.size)
        assertTrue("source=GRAY_ZONE" in logLines.single())
        assertFalse(answer.id.toString() in logLines.single() || student.toString() in logLines.single())

        val plain = start()
        modelSays(ToxicityVerdict.Clean(review = false, modelVersion = model))
        service.submit(plain.id, UUID.randomUUID(), narrative("보통 합성 답"))
        val skipped = start()
        modelSays(ToxicityVerdict.Skipped(ToxicitySkipReason.TIMEOUT))
        service.submit(skipped.id, UUID.randomUUID(), narrative("검사 안 된 합성 답"))
        assertEquals(listOf(0, 0), listOf(reviewsOf(plain.id), reviewsOf(skipped.id)))

        val blocked = start()
        modelSays(ToxicityVerdict.Flagged)
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE") {
            service.submit(blocked.id, UUID.randomUUID(), narrative("막힐 합성 답"))
        }
        assertEquals(0, reviewsOf(blocked.id))
    }

    @Test
    fun `분류 모델에는 입력 방식의 학생이 쓴 칸만 보냄`() {
        val attempt = start(inputType = "ESSAY", grade = 5)
        val essay = SubmitCommand(InputType.ESSAY, AnswerContent(text = "안 쓰는 칸", essay = Essay("주장", listOf("근거1", "근거2"), "반박")), false, null)

        runCatching { service.submit(attempt.id, UUID.randomUUID(), essay) }

        verify(toxicity).check(listOf("주장", "근거1", "근거2", "반박"))
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

    private fun timeOf(answerId: UUID) = jdbc.queryForMap("SELECT thinking_seconds, writing_seconds FROM answer WHERE id = ?", answerId)
        .let { it["thinking_seconds"] to it["writing_seconds"] }

    @Test
    fun `생각·작성 시간은 답변마다 저장해 시도 상세에 보이고, 칸 없는 제출은 둘 다 null (#801)`() {
        val attempt = start()

        val first = service.submit(attempt.id, UUID.randomUUID(), narrative("처음").copy(thinkingSeconds = 95, writingSeconds = 240))
        val followup = followup(attempt.id, first.id)
        val second = service.submit(attempt.id, UUID.randomUUID(), narrative("보완", followupId = followup))

        assertEquals(95 to 240, first.thinkingSeconds to first.writingSeconds)
        assertEquals(95 to 240, timeOf(first.id))
        assertEquals(null to null, timeOf(second.id))
        assertEquals(
            listOf(95 to 240, null to null),
            attemptService.get(attempt.id).answers.map { it.thinkingSeconds to it.writingSeconds },
        )
    }

    @Test
    fun `0초·24시간은 저장하고, 하나만 오거나 음수·24시간 초과면 제출은 받고 둘 다 null`() {
        val stored = mapOf((0L to 0L) to (0 to 0), (86_400L to 86_400L) to (86_400 to 86_400))
        val dropped = listOf(95L to null, null to 240L, -1L to 240L, 95L to -5L, 86_401L to 240L, 95L to Long.MAX_VALUE)
        (stored.keys + dropped).forEach { (thinking, writing) ->
            val attempt = start()
            val answer = service.submit(attempt.id, UUID.randomUUID(), narrative("답").copy(thinkingSeconds = thinking, writingSeconds = writing))
            assertEquals(stored[thinking to writing] ?: (null to null), timeOf(answer.id), "$thinking, $writing")
        }
    }

    @Test
    fun `고르기 방식과 보호자 받아쓰기는 값이 와도 null, 풀이 단계·논술은 저장`() {
        val choices = """[{"id": "a", "label": "물"}, {"id": "b", "label": "얼음"}]"""
        val categories = """[{"id": "액체", "label": "액체"}, {"id": "고체", "label": "고체"}]"""
        val cases = listOf(
            Triple("CHOICE" to 3, SubmitCommand(InputType.CHOICE, AnswerContent(choiceIds = listOf("b")), false, null), false),
            Triple("ORDERING" to 3, SubmitCommand(InputType.ORDERING, AnswerContent(choiceIds = listOf("b", "a")), false, null), false),
            Triple(
                "CLASSIFICATION" to 3,
                SubmitCommand(InputType.CLASSIFICATION, AnswerContent(assignments = listOf(Assignment("a", "액체"), Assignment("b", "고체"))), false, null),
                false,
            ),
            Triple("NARRATIVE" to 3, SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "엄마가 받아 씀"), true, null), false),
            Triple("SOLUTION_STEPS" to 3, SubmitCommand(InputType.SOLUTION_STEPS, AnswerContent(finalAnswer = "6", steps = listOf("2씩 3묶음")), false, null), true),
            Triple("ESSAY" to 5, SubmitCommand(InputType.ESSAY, AnswerContent(essay = Essay("찬성", listOf("안전", "편리"), "그래도 필요")), false, null), true),
        )
        cases.forEach { (type, command, measured) ->
            val mission = rows.mission(inputType = type.first, grade = type.second, choices = choices, categories = categories)
            val attempt = attemptService.start(student, mission.id, type.second, demo = false).attempt
            val answer = service.submit(attempt.id, UUID.randomUUID(), command.copy(thinkingSeconds = 30, writingSeconds = 60))
            assertEquals(if (measured) 30 to 60 else null to null, timeOf(answer.id), "${type.first} 받아쓰기=${command.dictatedByGuardian}")
        }
    }

    @Test
    fun `같은 키 재요청은 시간만 달라도 같은 요청, 처음 저장한 시간을 그대로 돌려줌`() {
        val attempt = start()
        val key = UUID.randomUUID()

        val first = service.submit(attempt.id, key, narrative("처음").copy(thinkingSeconds = 95, writingSeconds = 240))
        val again = service.submit(attempt.id, key, narrative("처음").copy(thinkingSeconds = 100, writingSeconds = 250))
        val withoutTime = service.submit(attempt.id, key, narrative("처음"))

        assertEquals(first, again)
        assertEquals(first, withoutTime)
        assertEquals(95 to 240, timeOf(first.id))
        assertEquals(1, count("SELECT count(*) FROM answer WHERE attempt_id = ?", attempt.id))
        assertError(HttpStatus.UNPROCESSABLE_ENTITY, "IDEMPOTENCY_KEY_REUSED") {
            service.submit(attempt.id, key, narrative("바꿈").copy(thinkingSeconds = 95, writingSeconds = 240))
        }
    }

    @Test
    fun `DB도 음수와 한쪽만 있는 시간을 막음 (V23 CHECK)`() {
        // 위반 하나로 시험 트랜잭션이 중단되므로 위반은 한 번만 내고, 나머지는 CHECK 정의로 확인
        val checks = jdbc.queryForList(
            "SELECT conname || ' ' || pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'answer'::regclass AND (conname LIKE 'ck_answer_%seconds' OR conname = 'ck_answer_time_pair') ORDER BY conname",
            String::class.java,
        )
        assertEquals(
            listOf(
                "ck_answer_thinking_seconds CHECK ((thinking_seconds >= 0))",
                "ck_answer_time_pair CHECK (((thinking_seconds IS NULL) = (writing_seconds IS NULL)))",
                "ck_answer_writing_seconds CHECK ((writing_seconds >= 0))",
            ),
            checks,
        )
        val answer = service.submit(start().id, UUID.randomUUID(), narrative("답"))
        assertThrows<DataIntegrityViolationException> {
            jdbc.update("UPDATE answer SET thinking_seconds = 1 WHERE id = ?", answer.id)
        }
    }

    @Test
    fun `답변 저장 DB 오류를 전역 예외 로그로 남겨도 답변 원문은 없고 제약 이름만 (NFR-SEC-05, #898)`(output: CapturedOutput) {
        val secret = "합성 비밀 답 원문 898"
        val attempt = start()
        val answer = Answer.next(
            null, attempt.id, null, InputType.NARRATIVE, AnswerContent(text = secret), secret,
            dictatedByGuardian = false, idempotencyKey = UUID.randomUUID(), now = java.time.Instant.now(),
        ).copy(thinkingSeconds = -1, writingSeconds = 1) // 서비스는 음수 시간을 버리므로 저장소로 바로 넣어 V23 CHECK 위반

        val error = assertThrows<DataIntegrityViolationException> { answerRepository.insert(answer) }
        GlobalExceptionHandler().handleUnexpected(error, MockHttpServletRequest())

        assertTrue("ck_answer_thinking_seconds" in output.out, "제약 이름은 남아 원인을 찾을 수 있음")
        assertFalse("합성 비밀" in output.all)
        assertFalse("Failing row" in output.all)
    }

    @Test
    fun `입력 방식마다 저장한 내용을 다시 읽어도 같은 키 재요청은 같은 답변`() {
        val choices = """[{"id": "a", "label": "물"}, {"id": "b", "label": "얼음"}]"""
        val categories = """[{"id": "액체", "label": "액체"}, {"id": "고체", "label": "고체"}]"""
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
            val mission = rows.mission(inputType = type.first, grade = type.second, choices = choices, categories = categories)
            val attempt = attemptService.start(student, mission.id, type.second, demo = false).attempt
            val key = UUID.randomUUID()

            val first = service.submit(attempt.id, key, command)

            assertEquals(first, service.submit(attempt.id, key, command), type.first)
            assertEquals(command.content, answerRepository.findLatest(attempt.id)?.content, type.first)
        }
    }

    @Test
    fun `보완 답변을 내도 이전 버전은 덮어쓰지 않음`() {
        val attempt = start()
        val first = service.submit(attempt.id, UUID.randomUUID(), narrative("처음 생각"))
        val row = { id: UUID -> jdbc.queryForObject("SELECT row_to_json(a)::text FROM answer a WHERE id = ?", String::class.java, id) }
        val before = row(first.id)

        val second = service.submit(attempt.id, UUID.randomUUID(), narrative("보완 1", followupId = followup(attempt.id, first.id, 1)))
        service.submit(attempt.id, UUID.randomUUID(), narrative("보완 2", followupId = followup(attempt.id, second.id, 2)))

        assertEquals(before, row(first.id))
        val versions = attemptService.get(attempt.id).answers
        assertEquals(listOf(1, 2, 3), versions.map { it.version })
        assertEquals(
            listOf("처음 생각", "보완 1", "보완 2"),
            versions.map { it.text },
        )
        assertEquals(first.submittedAt, versions.first().submittedAt)
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
