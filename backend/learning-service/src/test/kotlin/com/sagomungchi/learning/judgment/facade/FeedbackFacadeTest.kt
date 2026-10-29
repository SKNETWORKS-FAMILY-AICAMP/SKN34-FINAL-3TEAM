package com.sagomungchi.learning.judgment.facade

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.aResponse
import com.github.tomakehurst.wiremock.client.WireMock.okJson
import com.github.tomakehurst.wiremock.client.WireMock.post
import com.github.tomakehurst.wiremock.client.WireMock.postRequestedFor
import com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.Answer
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.Assignment
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.client.AiClient
import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.FollowupSource
import com.sagomungchi.learning.judgment.domain.FollowupType
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.NextAction
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.service.JudgmentService
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.mockito.ArgumentMatchers.any
import org.mockito.ArgumentMatchers.anyString
import org.mockito.BDDMockito.willThrow
import org.mybatis.spring.SqlSessionTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 피드백 흐름 (이슈 #25): 실제 PostgreSQL + WireMock ai (정상·보류·실패·유출 검사 실패) */
class FeedbackFacadeTest : PostgresRepositoryTest() {
    @Autowired lateinit var facade: FeedbackFacade
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var aiClient: AiClient
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var sqlSession: SqlSessionTemplate
    @Autowired lateinit var objectMapper: ObjectMapper
    @MockitoSpyBean lateinit var judgmentService: JudgmentService

    private lateinit var rows: TestRows
    private val student = UUID.randomUUID()
    private val choices = """[{"id": "c1", "label": "햇빛"}, {"id": "c2", "label": "물"}, {"id": "c3", "label": "흙"}]"""

    @BeforeEach
    fun prepare() {
        rows = TestRows(jdbc)
        actAs(student)
        ai.resetAll()
        aiClient.circuitBreaker.reset()
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    private fun actAs(studentId: UUID) =
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(studentId.toString()), "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"))

    private class Setup(val attempt: Attempt, val elements: List<UUID>)

    private fun setup(
        inputType: String,
        grade: Int = 3,
        elements: List<String> = listOf("원인"),
        answerKey: String? = null,
        forbiddenTerms: String? = null,
        categories: String? = null,
        answerUnit: String? = null,
        finalAnswer: Boolean = false,
    ): Setup {
        val mission = rows.mission(inputType = inputType, grade = grade, choices = choices, title = "화분 미션", categories = categories, answerUnit = answerUnit)
        val ids = rows.rubric(mission, elements, answerKey, forbiddenTerms, exampleAnswer = "예시 답", finalAnswer = finalAnswer)
        return Setup(attemptService.start(student, mission.id, grade, demo = false).attempt, ids)
    }

    private fun submit(attempt: Attempt, content: AnswerContent, inputType: InputType, followupId: UUID? = null): Answer =
        answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(inputType, content, false, followupId))

    private fun narrative(attempt: Attempt, text: String, followupId: UUID? = null) =
        submit(attempt, AnswerContent(text = text), InputType.NARRATIVE, followupId)

    private fun judgeReturns(result: String, elements: List<Pair<UUID, String?>>, heldReason: String? = null) {
        val items = elements.joinToString(",") { (id, quote) ->
            """{"elementId":"$id","quote":${quote?.let { "\"$it\"" } ?: "null"},"verified":${quote != null},"satisfied":${quote != null}}"""
        }
        ai.stubFor(
            post(urlEqualTo("/internal/judgments")).willReturn(
                okJson(
                    """{"result":"$result","elements":[$items],"heldReason":${heldReason?.let { "\"$it\"" } ?: "null"},"trial":true,
                        "versions":{"mission":null,"rubric":null,"model":"gpt-test","prompt":"judge@2"}}""",
                ),
            ),
        )
    }

    private fun followupReturns(type: String, question: String?, source: String = "LLM") {
        ai.stubFor(
            post(urlEqualTo("/internal/followups")).willReturn(
                okJson(
                    """{"type":"$type","question":${question?.let { "\"$it\"" } ?: "null"},"source":"$source",
                        "leakCheck":{"passed":${question != null}},"versions":{"model":"gpt-test","prompt":"followup@4"}}""",
                ),
            ),
        )
    }

    private fun aiUnavailable(path: String, retryable: Boolean = true) = ai.stubFor(
        post(urlEqualTo(path)).willReturn(
            aResponse().withStatus(503).withHeader("Content-Type", "application/problem+json")
                .withBody("""{"code":"AI_UNAVAILABLE","retryable":$retryable}"""),
        ),
    )

    private fun calls(path: String) = ai.countRequestsMatching(postRequestedFor(urlEqualTo(path)).build()).count

    private fun lastBody(path: String): JsonNode = objectMapper.readTree(ai.findAll(postRequestedFor(urlEqualTo(path))).last().bodyAsString)

    private fun judgment(answerId: UUID): Map<String, Any?> = jdbc.queryForMap("SELECT * FROM judgment WHERE answer_id = ?", answerId)

    private fun followupRow(answerId: UUID): Map<String, Any?> = jdbc.queryForMap(
        "SELECT f.* FROM followup f JOIN judgment j ON j.id = f.judgment_id WHERE j.answer_id = ?", answerId,
    )

    @Test
    fun `고르기 정답은 규칙 판정, ai를 부르지 않고 되묻기 없이 FINISH`() {
        val setup = setup("CHOICE", answerKey = """{"choiceIds": ["c2"]}""")
        val answer = submit(setup.attempt, AnswerContent(choiceIds = listOf("c2")), InputType.CHOICE)

        val result = facade.feedback(answer.id)

        assertEquals(ProcessStatus.DONE to JudgmentResult.CORRECT, result.status to result.judgment?.result)
        assertEquals(listOf(NextAction.FINISH), result.nextActions)
        assertNull(result.followup)
        val element = result.judgment!!.elements.single()
        assertEquals(listOf(setup.elements[0], "원인", true, "물", ElementSource.ANSWER_KEY), listOf(element.elementId, element.label, element.satisfied, element.quote, element.sourceType))
        assertEquals(false, result.judgment!!.trial)
        assertNull(result.versions!!.model)
        assertTrue(result.versions!!.mission.endsWith("@1"))
        assertEquals(0, calls("/internal/judgments") + calls("/internal/followups"))
        assertEquals(listOf("RULE", null, null), judgment(answer.id).let { listOf(it["method"], it["model_version"], it["failure_code"]) })
        assertEquals("4bf92f3577b34da6a3ce929d0e0e4736", judgment(answer.id)["trace_id"])
    }

    @Test
    fun `고르기 오답은 다시 살펴보기 되묻기, 유출 검사용 정답은 선택지 이름이고 학생 ID는 본문에 없음`() {
        val setup = setup("CHOICE", answerKey = """{"choiceIds": ["c2"]}""", forbiddenTerms = """["물이 부족"]""")
        followupReturns("LOOK_AGAIN", "두 화분에서 다른 점을 다시 볼까요?")
        val answer = submit(setup.attempt, AnswerContent(choiceIds = listOf("c1")), InputType.CHOICE)

        val result = facade.feedback(answer.id)

        assertEquals(JudgmentResult.RETHINK, result.judgment?.result)
        assertEquals(listOf(NextAction.ANSWER_FOLLOWUP, NextAction.FINISH), result.nextActions)
        assertEquals(FollowupType.LOOK_AGAIN to FollowupSource.LLM, result.followup!!.type to result.followup!!.source)
        val body = lastBody("/internal/followups")
        assertEquals(listOf("물"), body["rubric"]["answerKey"].map { it.asText() })
        assertEquals(listOf("물이 부족"), body["rubric"]["forbiddenTerms"].map { it.asText() })
        assertEquals("ANSWER" to "햇빛", body["timeline"].single().let { it["kind"].asText() to it["text"].asText() })
        assertEquals(listOf("화분 미션", "ANALYZE", "3"), listOf(body["mission"]["title"].asText(), body["mission"]["thinkingType"].asText(), body["grade"].asText()))
        assertFalse(body.toString().contains(student.toString()))
        assertEquals(listOf(true, "gpt-test", "followup@4", null), followupRow(answer.id).let { listOf(it["leak_check_passed"], it["model_version"], it["prompt_version"], it["bank_question_id"]) })
    }

    @Test
    fun `서술은 ai 판정 요소를 근거와 함께 저장하고 판정·되묻기 버전을 따로 남김`() {
        val setup = setup("NARRATIVE", elements = listOf("주장", "까닭"))
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "더 놀 수 있어서", setup.elements[1] to null))
        followupReturns("TELL_MORE", "왜 그렇게 생각했나요?")
        val answer = narrative(setup.attempt, "더 놀 수 있어서 좋아요")

        val result = facade.feedback(answer.id)

        assertEquals(JudgmentResult.PARTIAL, result.judgment?.result)
        assertEquals(
            listOf(Triple(true, "더 놀 수 있어서", ElementSource.AI_OBSERVATION), Triple(false, null, null)),
            result.judgment!!.elements.map { Triple(it.satisfied, it.quote, it.sourceType) },
        )
        assertEquals("gpt-test" to "judge@2", result.versions!!.model to result.versions!!.prompt)
        assertEquals(listOf("LLM", true, "gpt-test", "judge@2"), judgment(answer.id).let { listOf(it["method"], it["trial"], it["model_version"], it["prompt_version"]) })
        assertEquals("followup@4", followupRow(answer.id)["prompt_version"])
        val judge = lastBody("/internal/judgments")
        assertEquals(listOf("더 놀 수 있어서 좋아요", "NARRATIVE", "3"), listOf(judge["answerText"].asText(), judge["inputType"].asText(), judge["grade"].asText()))
        assertEquals(setup.elements.map { it.toString() }, judge["rubric"]["elements"].map { it["elementId"].asText() })
        assertEquals(result.versions!!.mission, judge["versions"]["mission"].asText())
    }

    @Test
    fun `보류는 정상 처리(DONE)로 사유를 저장하고 더 말해 보기 되묻기`() {
        val setup = setup("NARRATIVE")
        judgeReturns("HELD", emptyList(), heldReason = "TOO_SHORT")
        followupReturns("TELL_MORE", "조금 더 이야기해 줄래요?")
        val answer = narrative(setup.attempt, "좋아요")

        val result = facade.feedback(answer.id)

        assertEquals(listOf(ProcessStatus.DONE, JudgmentResult.HELD, "TOO_SHORT"), listOf(result.status, result.judgment?.result, result.judgment?.heldReason))
        assertEquals(emptyList(), result.judgment!!.elements)
        assertEquals(FollowupType.TELL_MORE, result.followup?.type)
        assertEquals("HELD" to "TOO_SHORT", judgment(answer.id).let { it["result"] to it["held_reason"] })
    }

    @Test
    fun `유출 검사가 재생성까지 실패하면 같은 유형의 질문 은행 질문, 같은 시도에서는 안 쓴 질문부터`() {
        val first = rows.bankQuestion("TELL_MORE", "생각을 조금 더 말해 줄래요?", minutesLater = 1)
        val second = rows.bankQuestion("TELL_MORE", "어떤 점에서 그렇게 생각했나요?", minutesLater = 2)
        rows.bankQuestion("LOOK_AGAIN", "다시 살펴볼까요?")
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서"))
        followupReturns("TELL_MORE", null, source = "LLM_RETRY")

        val v1 = narrative(setup.attempt, "놀 수 있어서 좋아요")
        val r1 = facade.feedback(v1.id)
        val v2 = narrative(setup.attempt, "친구와 더 놀 수 있어서요", followupId = r1.followup!!.followupId)
        val r2 = facade.feedback(v2.id)

        assertEquals(listOf("생각을 조금 더 말해 줄래요?", "어떤 점에서 그렇게 생각했나요?"), listOf(r1, r2).map { it.followup!!.question })
        assertEquals(listOf(FollowupSource.BANK, FollowupSource.BANK), listOf(r1, r2).map { it.followup!!.source })
        assertEquals(listOf(false, first, null), followupRow(v1.id).let { listOf(it["leak_check_passed"], it["bank_question_id"], it["model_version"]) })
        assertEquals(second, followupRow(v2.id)["bank_question_id"])
        val timeline = lastBody("/internal/followups")["timeline"].map { it["kind"].asText() to it["text"].asText() }
        assertEquals(listOf("ANSWER" to "놀 수 있어서 좋아요", "FOLLOWUP" to "생각을 조금 더 말해 줄래요?", "ANSWER" to "친구와 더 놀 수 있어서요"), timeline)
    }

    @Test
    fun `ai 실패는 FAILED와 503 retryable, 답변은 그대로이고 재요청하면 다시 실행, DONE 뒤 재요청은 같은 결과`() {
        val setup = setup("NARRATIVE")
        aiUnavailable("/internal/judgments", retryable = true)
        val answer = narrative(setup.attempt, "더 놀 수 있어서 좋아요")

        val error = assertThrows<AiUnavailableException> { facade.feedback(answer.id) }

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE to true, error.status to error.retryable)
        assertEquals(listOf("FAILED", "AI_UNAVAILABLE", 1), judgment(answer.id).let { listOf(it["process_status"], it["failure_code"], it["retry_count"]) })
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM answer WHERE id = ?", Int::class.java, answer.id))
        assertEquals(ProcessStatus.FAILED, attemptService.get(setup.attempt.id).feedbacks.getValue(answer.id).status)

        judgeReturns("CORRECT", listOf(setup.elements[0] to "더 놀 수 있어서"))
        followupReturns("ONE_STEP_MORE", "반대 친구는 어떻게 생각할까요?")
        val done = facade.feedback(answer.id)
        val again = facade.feedback(answer.id)

        assertEquals(JudgmentResult.CORRECT, done.judgment?.result)
        assertEquals(done, again)
        assertEquals(2 to 1, calls("/internal/judgments") to calls("/internal/followups"))
        assertEquals(listOf("DONE", null, 1), judgment(answer.id).let { listOf(it["process_status"], it["failure_code"], it["retry_count"]) })
    }

    @Test
    fun `되묻기만 실패해도 판정을 저장하지 않고 FAILED, 인증 실패처럼 다시 해도 안 되는 오류는 retryable false`() {
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서"))
        aiUnavailable("/internal/followups", retryable = false)
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")

        val error = assertThrows<AiUnavailableException> { facade.feedback(answer.id) }

        assertFalse(error.retryable)
        assertEquals(listOf("FAILED", null), judgment(answer.id).let { listOf(it["process_status"], it["result"]) })
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM judgment_element e JOIN judgment j ON j.id = e.judgment_id WHERE j.answer_id = ?", Int::class.java, answer.id))
    }

    @Test
    fun `다른 요청이 유효한 리스로 처리 중이면 RUNNING만, 리스가 끝났으면 다시 가져가 실행`() {
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서"))
        followupReturns("TELL_MORE", "더 말해 줄래요?")
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")
        jdbc.update("UPDATE judgment SET process_status = 'RUNNING', lease_until = now() + interval '1 minute' WHERE answer_id = ?", answer.id)
        sqlSession.clearCache()

        assertEquals(FeedbackResult.inProgress(ProcessStatus.RUNNING), facade.feedback(answer.id))
        assertEquals(0, calls("/internal/judgments"))

        jdbc.update("UPDATE judgment SET lease_until = now() - interval '1 second' WHERE answer_id = ?", answer.id)
        sqlSession.clearCache()
        assertEquals(ProcessStatus.DONE, facade.feedback(answer.id).status)
    }

    @Test
    fun `되묻기는 시도당 2회까지, 두 번째 되묻기에 답한 판정은 FINISH만`() {
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서"))
        followupReturns("TELL_MORE", "더 말해 줄래요?")

        val v1 = narrative(setup.attempt, "놀 수 있어서 좋아요")
        val f1 = facade.feedback(v1.id).followup!!.followupId
        val v2 = narrative(setup.attempt, "친구와 놀 수 있어서요", f1)
        val f2 = facade.feedback(v2.id).followup!!.followupId
        val v3 = narrative(setup.attempt, "친구와 이야기도 할 수 있어서요", f2)
        val r3 = facade.feedback(v3.id)

        assertNull(r3.followup)
        assertEquals(listOf(NextAction.FINISH), r3.nextActions)
        assertEquals(2, calls("/internal/followups"))
        val detail = attemptService.get(setup.attempt.id)
        assertEquals(listOf(NextAction.FINISH), detail.feedbacks.getValue(v1.id).nextActions)
        assertEquals(listOf(NextAction.FINISH), detail.feedbacks.getValue(v3.id).nextActions)
    }

    @Test
    fun `풀이 단계는 최종 답 규칙과 풀이 ai 판정을 합치고, 수학은 정답이어도 한 걸음 더`() {
        val setup = setup("SOLUTION_STEPS", elements = listOf("문제 파악", "방법 세우기"), answerKey = """{"finalAnswer": "30 m²"}""")
        judgeReturns("CORRECT", listOf(setup.elements[0] to "넓이를 구함", setup.elements[1] to "나누어 구함"))
        followupReturns("ONE_STEP_MORE", "다른 방법도 있을까요?")

        val right = submit(setup.attempt, AnswerContent(finalAnswer = "30", steps = listOf("넓이를 구함", "나누어 구함")), InputType.SOLUTION_STEPS)
        val correct = facade.feedback(right.id)

        assertEquals(JudgmentResult.CORRECT, correct.judgment?.result)
        assertEquals(FollowupType.ONE_STEP_MORE, correct.followup?.type)
        assertEquals(listOf("30 m²"), lastBody("/internal/followups")["rubric"]["answerKey"].map { it.asText() })

        val wrong = submit(setup.attempt, AnswerContent(finalAnswer = "32 m²", steps = listOf("넓이를 구함", "나누어 구함")), InputType.SOLUTION_STEPS, correct.followup!!.followupId)
        assertEquals(JudgmentResult.PARTIAL, facade.feedback(wrong.id).judgment?.result)
    }

    @Test
    fun `마무리한 시도에 남은 답변은 판정만 하고 되묻기 없이 다음 행동 없음`() {
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서"))
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")
        jdbc.update("UPDATE attempt SET finished_at = now() WHERE id = ?", setup.attempt.id)
        sqlSession.clearCache()

        val result = facade.feedback(answer.id)

        assertEquals(JudgmentResult.PARTIAL, result.judgment?.result)
        assertNull(result.followup)
        assertEquals(emptyList(), result.nextActions)
        assertEquals(0, calls("/internal/followups"))
    }

    @Test
    fun `ai가 기준표에 없는 요소를 돌려주면 AI_BAD_RESPONSE로 FAILED`() {
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(UUID.randomUUID() to "놀 수 있어서"))
        // 되묻기는 정상이라 다른 단계에서 우연히 실패하지 않음. 판정 응답을 읽을 때 막혀 되묻기를 부르지 않아야 함
        followupReturns("TELL_MORE", "더 말해 줄래요?")
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")

        assertFalse(assertThrows<AiUnavailableException> { facade.feedback(answer.id) }.retryable)
        assertEquals("FAILED" to "AI_BAD_RESPONSE", judgment(answer.id).let { it["process_status"] to it["failure_code"] })
        assertEquals(0, calls("/internal/followups"))
    }

    @Test
    fun `ai가 근거가 확인되지 않은 요소를 충족으로 주면 AI_BAD_RESPONSE로 FAILED`() {
        val setup = setup("NARRATIVE")
        ai.stubFor(
            post(urlEqualTo("/internal/judgments")).willReturn(
                okJson(
                    """{"result":"CORRECT","elements":[{"elementId":"${setup.elements[0]}","quote":"놀 수 있어서","verified":false,"satisfied":true}],
                        "heldReason":null,"trial":true,"versions":{"model":"m","prompt":"judge@2"}}""",
                ),
            ),
        )
        followupReturns("ONE_STEP_MORE", "반대 친구는 어떻게 생각할까요?")
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")

        assertThrows<AiUnavailableException> { facade.feedback(answer.id) }
        assertEquals("FAILED" to "AI_BAD_RESPONSE", judgment(answer.id).let { it["process_status"] to it["failure_code"] })
        assertEquals(0, calls("/internal/followups"))
    }

    @Test
    fun `ai가 요소를 중복으로 주거나 빠뜨리면 AI_BAD_RESPONSE, 되묻기는 부르지 않음`() {
        val setup = setup("NARRATIVE", elements = listOf("주장", "까닭"))
        followupReturns("TELL_MORE", "더 말해 줄래요?")
        val duplicated = narrative(setup.attempt, "놀 수 있어서 좋아요")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서", setup.elements[0] to "놀 수 있어서"))
        assertThrows<AiUnavailableException> { facade.feedback(duplicated.id) }

        val other = setup("NARRATIVE", elements = listOf("주장", "까닭"))
        val missing = narrative(other.attempt, "놀 수 있어서 좋아요")
        judgeReturns("PARTIAL", listOf(other.elements[0] to "놀 수 있어서"))
        assertThrows<AiUnavailableException> { facade.feedback(missing.id) }

        assertEquals(listOf("AI_BAD_RESPONSE", "AI_BAD_RESPONSE"), listOf(duplicated, missing).map { judgment(it.id)["failure_code"] })
        assertEquals(0, calls("/internal/followups"))
    }

    @Test
    fun `질문 은행이 비어 있으면 INTERNAL_ERROR로 FAILED, 리스를 풀어 다시 요청할 수 있음`() {
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서"))
        followupReturns("TELL_MORE", null, source = "LLM_RETRY")
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")

        assertThrows<IllegalStateException> { facade.feedback(answer.id) }

        assertEquals(listOf("FAILED", "INTERNAL_ERROR", 1), judgment(answer.id).let { listOf(it["process_status"], it["failure_code"], it["retry_count"]) })
        rows.bankQuestion("TELL_MORE", "생각을 조금 더 말해 줄래요?")
        assertEquals(FollowupSource.BANK, facade.feedback(answer.id).followup?.source)
    }

    @Test
    fun `실패 기록이 실패해도 ai 실패는 그대로 503 retryable로 응답하고 기록 오류는 suppressed로 붙임`() {
        val answer = narrative(setup("NARRATIVE").attempt, "놀 수 있어서 좋아요")
        val recordError = IllegalStateException("실패 기록 오류")
        willThrow(recordError).given(judgmentService).markFailed(anyJudgment(), anyString())
        aiUnavailable("/internal/judgments")

        val error = assertThrows<AiUnavailableException> { facade.feedback(answer.id) }

        assertTrue(error.retryable)
        assertEquals(listOf<Throwable>(recordError), error.suppressed.toList())
        assertEquals("RUNNING", judgment(answer.id)["process_status"])
    }

    @Test
    fun `실패 기록이 실패해도 예상 못 한 오류는 원래 예외 그대로 던짐`() {
        val setup = setup("NARRATIVE")
        judgeReturns("PARTIAL", listOf(setup.elements[0] to "놀 수 있어서"))
        followupReturns("TELL_MORE", null, source = "LLM_RETRY")
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")
        val recordError = IllegalStateException("실패 기록 오류")
        willThrow(recordError).given(judgmentService).markFailed(anyJudgment(), anyString())

        val error = assertThrows<IllegalStateException> { facade.feedback(answer.id) }

        assertTrue(error.message.orEmpty().startsWith("질문 은행에"))
        assertEquals(listOf<Throwable>(recordError), error.suppressed.toList())
    }

    /** Kotlin 매개변수는 null을 받지 않아 Mockito 매처 자리에 임시 값을 넣음 (매칭은 매처로 함) */
    private fun anyJudgment(): Judgment =
        any(Judgment::class.java) ?: Judgment(UUID.randomUUID(), UUID.randomUUID(), ProcessStatus.RUNNING, null, 0)

    @Test
    fun `순서 문항은 순서까지 맞아야 정답, 유출 검사용 정답은 정답 순서 전체`() {
        val setup = setup("ORDERING", answerKey = """{"choiceIds": ["c3", "c1", "c2"]}""")
        followupReturns("LOOK_AGAIN", "규칙을 다시 볼까요?")

        val wrong = facade.feedback(submit(setup.attempt, AnswerContent(choiceIds = listOf("c1", "c3", "c2")), InputType.ORDERING).id)

        assertEquals(JudgmentResult.RETHINK, wrong.judgment?.result)
        assertEquals("햇빛 → 흙 → 물", wrong.judgment!!.elements.single().quote)
        assertEquals(listOf("흙, 햇빛, 물"), lastBody("/internal/followups")["rubric"]["answerKey"].map { it.asText() })
        val right = submit(setup.attempt, AnswerContent(choiceIds = listOf("c3", "c1", "c2")), InputType.ORDERING, wrong.followup!!.followupId)
        assertEquals(JudgmentResult.CORRECT to listOf(NextAction.FINISH), facade.feedback(right.id).let { it.judgment?.result to it.nextActions })
    }

    @Test
    fun `풀이 단계는 최종 답·풀이 둘 다 아니면 RETHINK, ai가 보류하면 최종 답과 무관하게 보류`() {
        val key = """{"finalAnswer": "30 m²"}"""
        val rethink = setup("SOLUTION_STEPS", elements = listOf("문제 파악"), answerKey = key)
        judgeReturns("RETHINK", listOf(rethink.elements[0] to null))
        followupReturns("LOOK_AGAIN", "구할 것을 다시 볼까요?")
        val both = submit(rethink.attempt, AnswerContent(finalAnswer = "12", steps = listOf("더함")), InputType.SOLUTION_STEPS)
        assertEquals(JudgmentResult.RETHINK, facade.feedback(both.id).judgment?.result)

        val held = setup("SOLUTION_STEPS", elements = listOf("문제 파악"), answerKey = key)
        judgeReturns("HELD", emptyList(), heldReason = "TOO_SHORT")
        val short = submit(held.attempt, AnswerContent(finalAnswer = "30", steps = listOf("곱")), InputType.SOLUTION_STEPS)
        assertEquals(JudgmentResult.HELD to "TOO_SHORT", facade.feedback(short.id).judgment!!.let { it.result to it.heldReason })
    }

    @Test
    fun `다른 학생의 답변은 403, 없는 답변은 404`() {
        val setup = setup("NARRATIVE")
        val answer = narrative(setup.attempt, "놀 수 있어서 좋아요")

        actAs(UUID.randomUUID())
        assertEquals("FORBIDDEN", assertThrows<BusinessException> { facade.feedback(answer.id) }.code)
        assertEquals("NOT_FOUND", assertThrows<BusinessException> { facade.feedback(UUID.randomUUID()) }.code)
        assertEquals("PENDING", judgment(answer.id)["process_status"])
        org.mockito.Mockito.verifyNoInteractions(paymentUsage)
    }

    @Test fun `owned feedback reserves premium use and marks it complete only after DONE`() {
        val setup=setup("CHOICE",answerKey="""{"choiceIds":["c2"]}""")
        val answer=submit(setup.attempt,AnswerContent(choiceIds=listOf("c2")),InputType.CHOICE)
        val reservation=UUID.randomUUID()
        org.mockito.Mockito.`when`(paymentUsage.begin(student,answer.id)).thenReturn(reservation)
        assertEquals(ProcessStatus.DONE,facade.feedback(answer.id).status)
        org.mockito.Mockito.verify(paymentUsage).complete(student,reservation)
    }

    @Test fun `refund freeze rejects feedback before acquiring a judgment lease`() {
        val setup=setup("CHOICE",answerKey="""{"choiceIds":["c2"]}""")
        val answer=submit(setup.attempt,AnswerContent(choiceIds=listOf("c2")),InputType.CHOICE)
        org.mockito.Mockito.`when`(paymentUsage.begin(student,answer.id)).thenThrow(BusinessException(HttpStatus.CONFLICT,"REFUND_IN_PROGRESS","환불 확인 중"))
        assertEquals("REFUND_IN_PROGRESS",assertThrows<BusinessException> { facade.feedback(answer.id) }.code)
        assertEquals("PENDING",judgment(answer.id)["process_status"])
    }

    companion object {
        private val ai = WireMockServer(options().dynamicPort()).apply { start() }

        @JvmStatic
        @DynamicPropertySource
        fun aiUrl(registry: DynamicPropertyRegistry) {
            registry.add("app.services.ai") { ai.baseUrl() }
        }
    }

    @Test
    fun `풀이 단계 최종 답 요소는 ai에 보내지 않고 정답 키로 기록, 답이 틀리면 PARTIAL에 최종 답 미충족 (FN-JDG-02)`() {
        val setup = setup(
            "SOLUTION_STEPS", elements = listOf("문제 파악", "방법 세우기"), answerKey = """{"finalAnswer": "30"}""",
            answerUnit = "m²", finalAnswer = true,
        )
        val (steps, finalId) = setup.elements.take(2) to setup.elements.last()
        judgeReturns("CORRECT", listOf(steps[0] to "넓이를 구함", steps[1] to "나누어 구함"))
        followupReturns("LOOK_AGAIN", "답을 다시 확인해 볼까요?")

        val wrong = submit(setup.attempt, AnswerContent(finalAnswer = "28", steps = listOf("넓이를 구함", "나누어 구함")), InputType.SOLUTION_STEPS)
        val partial = facade.feedback(wrong.id)

        assertEquals(JudgmentResult.PARTIAL, partial.judgment?.result)
        assertEquals(steps.map { it.toString() }, lastBody("/internal/judgments")["rubric"]["elements"].map { it["elementId"].asText() })
        val missed = partial.judgment!!.elements.single { it.elementId == finalId }
        assertEquals(listOf<Any?>(false, "28", ElementSource.ANSWER_KEY), listOf(missed.satisfied, missed.quote, missed.sourceType))
        val followupRubric = lastBody("/internal/followups")["rubric"]
        assertEquals(listOf("30 m²"), followupRubric["answerKey"].map { it.asText() })
        assertTrue(followupRubric["elements"].any { it["elementId"].asText() == finalId.toString() })
        assertTrue(lastBody("/internal/judgments")["answerText"].asText().endsWith("최종 답: 28 m²"))

        val right = submit(setup.attempt, AnswerContent(finalAnswer = "30", steps = listOf("넓이를 구함", "나누어 구함")), InputType.SOLUTION_STEPS, partial.followup!!.followupId)
        val correct = facade.feedback(right.id)
        assertEquals(JudgmentResult.CORRECT, correct.judgment?.result)
        assertEquals(true to "30", correct.judgment!!.elements.single { it.elementId == finalId }.let { it.satisfied to it.quote })
    }

    @Test
    fun `풀이 단계를 ai가 보류하면 최종 답 요소도 남기지 않음`() {
        val setup = setup("SOLUTION_STEPS", elements = listOf("문제 파악"), answerKey = """{"finalAnswer": "30"}""", finalAnswer = true)
        judgeReturns("HELD", emptyList(), heldReason = "TOO_SHORT")
        followupReturns("TELL_MORE", "어떻게 구했는지 더 말해 줄래요?")

        val short = submit(setup.attempt, AnswerContent(finalAnswer = "30", steps = listOf("곱")), InputType.SOLUTION_STEPS)
        val held = facade.feedback(short.id)

        assertEquals(JudgmentResult.HELD, held.judgment?.result)
        assertEquals(emptyList(), held.judgment!!.elements)
    }

    @Test
    fun `분류는 모든 항목의 그룹이 정답 키와 같아야 정답, 없는 그룹은 422, 유출 검사용 정답은 선택지 이름과 그룹 이름`() {
        val setup = setup(
            "CLASSIFICATION",
            answerKey = """{"assignments": [{"choiceId": "c1", "categoryId": "g1"}, {"choiceId": "c2", "categoryId": "g1"}, {"choiceId": "c3", "categoryId": "g2"}]}""",
            categories = """[{"id": "g1", "label": "하늘에서 와요"}, {"id": "g2", "label": "땅에 있어요"}]""",
        )
        followupReturns("LOOK_AGAIN", "어디에서 오는지 다시 볼까요?")

        val wrong = submit(setup.attempt, AnswerContent(assignments = listOf(Assignment("c1", "g1"), Assignment("c2", "g2"), Assignment("c3", "g2"))), InputType.CLASSIFICATION)
        val rethink = facade.feedback(wrong.id)

        assertEquals(JudgmentResult.RETHINK, rethink.judgment?.result)
        assertEquals(0, calls("/internal/judgments"))
        assertEquals(
            listOf("햇빛: 하늘에서 와요", "물: 하늘에서 와요", "흙: 땅에 있어요"),
            lastBody("/internal/followups")["rubric"]["answerKey"].map { it.asText() },
        )
        val unknown = assertThrows<BusinessException> {
            submit(setup.attempt, AnswerContent(assignments = listOf(Assignment("c1", "g1"), Assignment("c2", "g1"), Assignment("c3", "g9"))), InputType.CLASSIFICATION, rethink.followup!!.followupId)
        }
        assertEquals(HttpStatus.UNPROCESSABLE_ENTITY to "ANSWER_INCOMPLETE", unknown.status to unknown.code)

        val right = submit(setup.attempt, AnswerContent(assignments = listOf(Assignment("c3", "g2"), Assignment("c1", "g1"), Assignment("c2", "g1"))), InputType.CLASSIFICATION, rethink.followup!!.followupId)
        assertEquals(JudgmentResult.CORRECT, facade.feedback(right.id).judgment?.result)
    }
}
