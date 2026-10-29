package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.Answer
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.domain.Difficulty
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.attempt.domain.RevealKind
import com.sagomungchi.learning.attempt.domain.SelfAssessmentItem
import com.sagomungchi.learning.attempt.domain.SelfCheck
import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

/** 이슈 #26 마무리·돌아보기·자기 평가 (FN-LRN-11~14, P04, sequence-diagram 3.3, state-diagram 3.2) */
class AttemptFinishTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: AttemptService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var jdbc: JdbcTemplate

    private lateinit var rows: TestRows
    private val student = UUID.randomUUID()
    private val choices = """[{"id": "c1", "label": "햇빛"}, {"id": "c2", "label": "물"}]"""

    @BeforeEach
    fun prepare() {
        rows = TestRows(jdbc)
        actAs(student)
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    private fun actAs(studentId: UUID) =
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(studentId.toString()), null))

    private fun assertError(status: HttpStatus, code: String, block: () -> Unit) {
        val error = assertThrows<BusinessException> { block() }
        assertEquals(status to code, error.status to error.code)
    }

    private class Setup(val attempt: Attempt, val elements: List<UUID>)

    private fun narrative(elements: List<String> = listOf("주장", "근거", "다른 관점")): Setup {
        val mission = rows.mission()
        val ids = rows.rubric(mission, elements, exampleAnswer = "예시 답")
        return Setup(service.start(student, mission.id, 3, demo = false).attempt, ids)
    }

    private fun submit(attempt: Attempt, text: String, followupId: UUID? = null): Answer =
        answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = text), false, followupId))

    private fun finishedAt(attempt: Attempt) =
        jdbc.queryForObject("SELECT finished_at IS NOT NULL FROM attempt WHERE id = ?", Boolean::class.java, attempt.id)

    @Test
    fun `처리 완료 판정이 없으면 마무리 409, 답변이 없어도·대기·처리 중·실패만 있어도 (P04)`() {
        val setup = narrative()
        assertError(HttpStatus.CONFLICT, "REVEAL_CONDITION_UNMET") { service.finish(setup.attempt.id) }

        val answer = submit(setup.attempt, "놀 수 있어서 좋아요")
        listOf("PENDING", "RUNNING", "FAILED").forEach { status ->
            jdbc.update("UPDATE judgment SET process_status = ? WHERE answer_id = ?", status, answer.id)
            assertError(HttpStatus.CONFLICT, "REVEAL_CONDITION_UNMET") { service.finish(setup.attempt.id) }
        }
        assertEquals(false, finishedAt(setup.attempt))
        assertNull(service.get(setup.attempt.id).revealed)
    }

    @Test
    fun `보류만 있어도 마무리, 열린 문제는 예시 답과 기준표 요소 전체 체크리스트 (FN-LRN-11)`() {
        val setup = narrative()
        rows.judged(submit(setup.attempt, "좋아요").id, result = "HELD", heldReason = "TOO_SHORT")

        val result = service.finish(setup.attempt.id)

        assertEquals("예시 답" to RevealKind.EXAMPLE, result.reveal to result.revealKind)
        assertEquals(listOf("주장", "근거", "다른 관점"), result.checklist.map { it.label })
        assertEquals(listOf(false, false, false), result.checklist.map { it.satisfied })
        assertEquals(true, finishedAt(setup.attempt))
    }

    @Test
    fun `체크리스트는 모든 답변의 판정을 합쳐 근거가 확인된 요소만 체크하고 가장 최근 구절을 표시`() {
        val (claim, reason, other) = narrative().let { it.elements to it }.let { (ids, setup) ->
            val first = submit(setup.attempt, "늘리면 좋아요. 놀 수 있어서")
            rows.judged(first.id, listOf(ids[0] to "늘리면 좋아요", ids[1] to null, ids[2] to null))
            val second = submit(setup.attempt, "더 놀면 집중이 잘 돼요", rows.followup(setup.attempt.id, first.id))
            rows.judged(second.id, listOf(ids[0] to null, ids[1] to "집중이 잘 돼요", ids[2] to null))
            service.finish(setup.attempt.id).checklist
        }

        assertEquals(ElementView(claim.elementId, "주장", true, "늘리면 좋아요", ElementSource.AI_OBSERVATION), claim)
        assertEquals("집중이 잘 돼요" to true, reason.quote to reason.satisfied)
        assertEquals(ElementView(other.elementId, "다른 관점", false, null, null), other)
    }

    @Test
    fun `되묻기에 답하지 않아도 마무리 가능 (api-spec 2·2 이대로 돌아보기)`() {
        val setup = narrative()
        val answer = submit(setup.attempt, "놀 수 있어서 좋아요")
        rows.judged(answer.id)
        rows.followup(setup.attempt.id, answer.id)

        assertNotNull(service.finish(setup.attempt.id).finishedAt)
    }

    @Test
    fun `닫힌 문제(고르기)는 정답으로 공개`() {
        val mission = rows.mission(inputType = "CHOICE", choices = choices)
        val element = rows.rubric(mission, listOf("고르는 생각"), answerKey = """{"choiceIds": ["c2"]}""", exampleAnswer = "정답: 물").single()
        val attempt = service.start(student, mission.id, 3, demo = false).attempt
        val answer = answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.CHOICE, AnswerContent(choiceIds = listOf("c2")), false, null))
        rows.judged(answer.id, listOf(element to "물"), result = "CORRECT")

        val result = service.finish(attempt.id)

        assertEquals("정답: 물" to RevealKind.ANSWER, result.reveal to result.revealKind)
        assertEquals(listOf(true), result.checklist.map { it.satisfied })
    }

    @Test
    fun `마무리를 다시 요청하면 기록을 바꾸지 않고 같은 결과, 마무리 뒤 답변 제출은 409`() {
        val setup = narrative()
        rows.judged(submit(setup.attempt, "놀 수 있어서 좋아요").id)
        val first = service.finish(setup.attempt.id)

        assertEquals(first, service.finish(setup.attempt.id))
        assertEquals(first.finishedAt, service.get(setup.attempt.id).attempt.finishedAt)
        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { submit(setup.attempt, "더 쓸래요") }
    }

    @Test
    fun `시도 상세는 마무리한 뒤에만 공개 내용, 돌아보기를 저장한 뒤에만 돌아보기`() {
        val setup = narrative()
        rows.judged(submit(setup.attempt, "놀 수 있어서 좋아요").id)
        assertNull(service.get(setup.attempt.id).revealed)

        val finished = service.finish(setup.attempt.id)
        assertEquals(finished, service.get(setup.attempt.id).revealed)
        assertNull(service.get(setup.attempt.id).reflection)

        service.saveReflection(setup.attempt.id, Reflection(Difficulty.NORMAL, "경험을 보탰어요"))
        assertEquals(Reflection(Difficulty.NORMAL, "경험을 보탰어요"), service.get(setup.attempt.id).reflection)
    }

    @Test
    fun `돌아보기는 마무리 전 409, 저장하면 같은 트랜잭션에서 학습 완료와 완료 시점 (FN-LRN-12·14)`() {
        val setup = narrative()
        rows.judged(submit(setup.attempt, "놀 수 있어서 좋아요").id)
        assertError(HttpStatus.CONFLICT, "REVEAL_CONDITION_UNMET") { service.saveReflection(setup.attempt.id, Reflection(Difficulty.EASY, null)) }
        service.finish(setup.attempt.id)

        service.saveReflection(setup.attempt.id, Reflection(Difficulty.HARD, null))

        assertEquals(AttemptStatus.COMPLETED, service.get(setup.attempt.id).attempt.status)
        val row = jdbc.queryForMap(
            "SELECT a.status, a.completed_at, r.difficulty, r.changed_text FROM attempt a JOIN reflection r ON r.attempt_id = a.id WHERE a.id = ?",
            setup.attempt.id,
        )
        assertEquals(listOf("COMPLETED", "HARD", null), listOf(row["status"], row["difficulty"], row["changed_text"]))
        assertNotNull(row["completed_at"])
    }

    @Test
    fun `완료한 시도에는 답변·초안·생각 열기·돌아보기·자기 평가 409, 마무리 결과 조회는 그대로 (state-diagram 3·2)`() {
        val setup = narrative()
        rows.judged(submit(setup.attempt, "놀 수 있어서 좋아요").id)
        val finished = service.finish(setup.attempt.id)
        service.saveReflection(setup.attempt.id, Reflection(Difficulty.EASY, null))

        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { submit(setup.attempt, "더 쓸래요") }
        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.saveDraft(setup.attempt.id, 1, DraftContent(emptyMap(), "")) }
        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.openHint(setup.attempt.id) }
        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.saveReflection(setup.attempt.id, Reflection(Difficulty.HARD, null)) }
        assertError(HttpStatus.CONFLICT, "ATTEMPT_CLOSED") { service.saveSelfAssessment(setup.attempt.id, listOf(SelfCheck(setup.elements[0], true))) }
        assertEquals(finished, service.finish(setup.attempt.id))
    }

    @Test
    fun `자기 평가는 마무리 뒤에 저장하고 AI 확인과 나란히, 다시 보내면 바꾸고 판정·답변은 그대로 (FN-LRN-13)`() {
        val setup = narrative()
        val answer = submit(setup.attempt, "늘리면 좋아요")
        rows.judged(answer.id, listOf(setup.elements[0] to "늘리면 좋아요", setup.elements[1] to null, setup.elements[2] to null))
        val (claim, reason, other) = setup.elements
        assertError(HttpStatus.CONFLICT, "REVEAL_CONDITION_UNMET") { service.saveSelfAssessment(setup.attempt.id, listOf(SelfCheck(claim, true))) }
        service.finish(setup.attempt.id)
        val before = recorded(answer.id)

        service.saveSelfAssessment(setup.attempt.id, listOf(SelfCheck(claim, true), SelfCheck(reason, true)))
        val items = service.saveSelfAssessment(setup.attempt.id, listOf(SelfCheck(reason, false)))

        assertEquals(
            listOf(
                SelfAssessmentItem(claim, "주장", true, true, "늘리면 좋아요"),
                SelfAssessmentItem(reason, "근거", false, false, null),
                SelfAssessmentItem(other, "다른 관점", null, false, null),
            ),
            items,
        )
        assertEquals(before, recorded(answer.id))
    }

    @Test
    fun `자기 평가 항목이 비었거나 같은 요소가 두 번이거나 기준표에 없는 요소면 400`() {
        val setup = narrative()
        rows.judged(submit(setup.attempt, "놀 수 있어서 좋아요").id)
        service.finish(setup.attempt.id)
        val claim = setup.elements[0]

        listOf(emptyList(), listOf(SelfCheck(claim, true), SelfCheck(claim, false)), listOf(SelfCheck(UUID.randomUUID(), true))).forEach { checks ->
            assertError(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED") { service.saveSelfAssessment(setup.attempt.id, checks) }
        }
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM self_assessment WHERE attempt_id = ?", Int::class.java, setup.attempt.id))
    }

    @Test
    fun `다른 학생의 시도는 마무리·돌아보기·자기 평가 403`() {
        val setup = narrative()
        rows.judged(submit(setup.attempt, "놀 수 있어서 좋아요").id)
        actAs(UUID.randomUUID())

        assertError(HttpStatus.FORBIDDEN, "FORBIDDEN") { service.finish(setup.attempt.id) }
        assertError(HttpStatus.FORBIDDEN, "FORBIDDEN") { service.saveReflection(setup.attempt.id, Reflection(Difficulty.EASY, null)) }
        assertError(HttpStatus.FORBIDDEN, "FORBIDDEN") { service.saveSelfAssessment(setup.attempt.id, listOf(SelfCheck(setup.elements[0], true))) }
    }

    /** 답변·판정·판정 요소 행 그대로 (자기 평가가 덮어쓰지 않음) */
    private fun recorded(answerId: UUID): List<Any?> = listOf(
        jdbc.queryForObject("SELECT row_to_json(a)::text FROM answer a WHERE id = ?", String::class.java, answerId),
        jdbc.queryForObject("SELECT row_to_json(j)::text FROM judgment j WHERE answer_id = ?", String::class.java, answerId),
        jdbc.queryForList(
            "SELECT row_to_json(e)::text FROM judgment_element e JOIN judgment j ON j.id = e.judgment_id WHERE j.answer_id = ? ORDER BY e.id",
            String::class.java, answerId,
        ),
    )
}
