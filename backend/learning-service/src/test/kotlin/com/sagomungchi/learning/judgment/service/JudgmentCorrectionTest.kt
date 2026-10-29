package com.sagomungchi.learning.judgment.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.domain.CorrectionCommand
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals

/** 판정 정정 (이슈 #80 완료 조건, api-spec 4.1·FN-SUP-03) */
class JudgmentCorrectionTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: JudgmentService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    private val admin = UUID.randomUUID()

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `정정하면 원판정·요소·답변은 그대로 두고 정정 행을 남김`() {
        val done = judged(result = "HELD", heldReason = "TOO_SHORT")
        val answerBefore = answerRow(done.answerId)
        val elementsBefore = elementRows(done.judgmentId)

        val reportId = UUID.randomUUID()
        val correction = asAdmin(done) { service.correct(done.judgmentId, command(reportId, JudgmentResult.CORRECT), UUID.randomUUID()) }

        assertEquals(JudgmentResult.HELD, correction.previous)
        assertEquals(JudgmentResult.CORRECT, correction.corrected)
        assertEquals(
            mapOf(
                "error_report_id" to reportId, "reason" to "규칙 판정 오류", "previous" to "HELD", "corrected" to "CORRECT",
                "corrected_by" to admin, "created_at" to correction.createdAt,
            ),
            jdbc.queryForMap(
                """SELECT error_report_id, reason, previous ->> 'result' AS previous, corrected ->> 'result' AS corrected,
                          corrected_by, created_at FROM judgment_correction WHERE id = ?""",
                correction.id,
            ).mapValues { (_, value) -> (value as? java.sql.Timestamp)?.toInstant() ?: value },
        )
        // 원판정·요소·답변은 그대로 (NFR-DAT-01)
        assertEquals(listOf("DONE", "HELD", "TOO_SHORT"), jdbc.queryForList(
            "SELECT process_status, result, held_reason FROM judgment WHERE id = ?", done.judgmentId,
        ).single().values.toList())
        assertEquals(elementsBefore, elementRows(done.judgmentId))
        assertEquals(answerBefore, answerRow(done.answerId))
    }

    @Test
    fun `다른 신고로 다시 정정하면 정정 전 결과는 앞선 정정 결과`() {
        val done = judged(result = "PARTIAL")

        asAdmin(done) { service.correct(done.judgmentId, command(UUID.randomUUID(), JudgmentResult.RETHINK), UUID.randomUUID()) }
        val second = asAdmin(done) { service.correct(done.judgmentId, command(UUID.randomUUID(), JudgmentResult.CORRECT), UUID.randomUUID()) }

        assertEquals(JudgmentResult.RETHINK, second.previous)
        assertEquals("PARTIAL", jdbc.queryForObject("SELECT result FROM judgment WHERE id = ?", String::class.java, done.judgmentId))
    }

    @Test
    fun `같은 키·같은 요청은 처음 정정을 그대로, 다른 본문이나 다른 판정이면 422`() {
        val done = judged()
        val other = judged(student = done.studentId)
        val key = UUID.randomUUID()
        val reportId = UUID.randomUUID()
        val first = asAdmin(done) { service.correct(done.judgmentId, command(reportId, JudgmentResult.CORRECT), key) }

        val again = asAdmin(done) { service.correct(done.judgmentId, command(reportId, JudgmentResult.CORRECT), key) }
        val otherBody = asAdmin(done) {
            assertThrows<BusinessException> { service.correct(done.judgmentId, command(reportId, JudgmentResult.RETHINK), key) }
        }
        val otherReason = asAdmin(done) {
            assertThrows<BusinessException> { service.correct(done.judgmentId, command(reportId, JudgmentResult.CORRECT, "다른 사유"), key) }
        }
        val otherJudgment = asAdmin(done) {
            assertThrows<BusinessException> { service.correct(other.judgmentId, command(reportId, JudgmentResult.CORRECT), key) }
        }

        assertEquals(first, again)
        assertEquals(List(3) { 422 to "IDEMPOTENCY_KEY_REUSED" }, listOf(otherBody, otherReason, otherJudgment).map { it.status.value() to it.code })
        assertEquals(1, corrections(done.judgmentId) + corrections(other.judgmentId))
    }

    @Test
    fun `같은 신고를 다른 키로 다시 정정하면 409, 다른 판정이어도 같음`() {
        val done = judged()
        val other = judged(student = done.studentId)
        val reportId = UUID.randomUUID()
        asAdmin(done) { service.correct(done.judgmentId, command(reportId, JudgmentResult.CORRECT), UUID.randomUUID()) }

        val errors = listOf(done, other).map { target ->
            asAdmin(done) { assertThrows<BusinessException> { service.correct(target.judgmentId, command(reportId, JudgmentResult.RETHINK), UUID.randomUUID()) } }
        }

        assertEquals(List(2) { 409 to "CORRECTION_REPORT_CONFLICT" }, errors.map { it.status.value() to it.code })
        assertEquals(1, corrections(done.judgmentId))
        assertEquals(0, corrections(other.judgmentId))
    }

    @Test
    fun `판정이 끝나기 전(PENDING·RUNNING·FAILED)이면 409, 정정 행 없음`() {
        val pending = submitted()
        val codes = listOf("PENDING", "RUNNING", "FAILED").map { status ->
            jdbc.update("UPDATE judgment SET process_status = ? WHERE id = ?", status, pending.judgmentId)
            asAdmin(pending) {
                assertThrows<BusinessException> { service.correct(pending.judgmentId, command(UUID.randomUUID(), JudgmentResult.CORRECT), UUID.randomUUID()) }
            }.let { it.status.value() to it.code }
        }

        assertEquals(List(3) { 409 to "JUDGMENT_STATE_CONFLICT" }, codes)
        assertEquals(0, corrections(pending.judgmentId))
    }

    @Test
    fun `없는 판정은 404, 범위에 다른 학생만 있으면 403`() {
        val done = judged()

        val missing = asAdmin(done) {
            assertThrows<BusinessException> { service.correct(UUID.randomUUID(), command(UUID.randomUUID(), JudgmentResult.CORRECT), UUID.randomUUID()) }
        }
        UserContextHolder.set(UserContext(admin.toString(), "ADMIN", setOf(UUID.randomUUID().toString()), null))
        val outOfScope = assertThrows<BusinessException> {
            service.correct(done.judgmentId, command(UUID.randomUUID(), JudgmentResult.CORRECT), UUID.randomUUID())
        }

        assertEquals(404 to "NOT_FOUND", missing.status.value() to missing.code)
        assertEquals(403 to "FORBIDDEN", outOfScope.status.value() to outOfScope.code)
        assertEquals(0, corrections(done.judgmentId))
    }

    private data class Done(val studentId: UUID, val attemptId: UUID, val answerId: UUID, val judgmentId: UUID, val elementId: UUID)

    private fun command(reportId: UUID, corrected: JudgmentResult, reason: String = "규칙 판정 오류") =
        CorrectionCommand(reportId, reason, corrected, admin)

    /** 서술 답변 하나를 제출해 판정 PENDING. 기준표 요소 ID와 함께 */
    private fun submitted(student: UUID = UUID.randomUUID()): Done {
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        val element = rows.rubric(mission).single()
        val attempt = asStudent(student) { attemptService.start(student, mission.id, 3, demo = false).attempt }
        val answer = asStudent(student) {
            answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "답"), false, null))
        }
        val judgmentId = jdbc.queryForObject("SELECT id FROM judgment WHERE answer_id = ?", UUID::class.java, answer.id)!!
        return Done(student, attempt.id, answer.id, judgmentId, element)
    }

    /** 판정 DONE(보류가 아니면 요소 하나 충족) + 아직 답하지 않은 되묻기 */
    private fun judged(student: UUID = UUID.randomUUID(), result: String = "PARTIAL", heldReason: String? = null): Done {
        val done = submitted(student)
        val rows = TestRows(jdbc)
        rows.judged(done.answerId, if (result == "HELD") emptyList() else listOf(done.elementId to "답"), result, heldReason)
        rows.followup(done.attemptId, done.answerId)
        return done
    }

    private fun <T> asAdmin(target: Done, block: () -> T): T {
        UserContextHolder.set(UserContext(admin.toString(), "ADMIN", setOf(target.studentId.toString()), null))
        return try { block() } finally { UserContextHolder.clear() }
    }

    private fun <T> asStudent(target: Done, block: () -> T): T = asStudent(target.studentId, block)

    private fun <T> asStudent(student: UUID, block: () -> T): T {
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        return try { block() } finally { UserContextHolder.clear() }
    }

    private fun answerRow(answerId: UUID) = jdbc.queryForMap("SELECT content::text, plain_text, version FROM answer WHERE id = ?", answerId)

    private fun elementRows(judgmentId: UUID) =
        jdbc.queryForList("SELECT rubric_element_id, quote, satisfied FROM judgment_element WHERE judgment_id = ? ORDER BY rubric_element_id", judgmentId)

    private fun corrections(judgmentId: UUID) =
        jdbc.queryForObject("SELECT count(*) FROM judgment_correction WHERE judgment_id = ?", Int::class.java, judgmentId)!!
}
