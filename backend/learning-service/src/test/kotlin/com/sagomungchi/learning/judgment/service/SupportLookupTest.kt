package com.sagomungchi.learning.judgment.service

import com.fasterxml.jackson.databind.ObjectMapper
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
import com.sagomungchi.learning.judgment.domain.SupportTarget
import com.sagomungchi.learning.judgment.domain.SupportTargetType
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse

/** 신고 지원 조회 (이슈 #146 완료 조건, api-spec 4.1·5.7) */
class SupportLookupTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: JudgmentService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper

    private val student = UUID.randomUUID()

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `세 대상 유형 모두 학생·시도, 판정은 판정 ID와 지금 보이는 결과, 되묻기는 만든 판정 ID`() {
        val first = submit()
        TestRows(jdbc).judged(first.answerId, result = "PARTIAL")
        val followupId = TestRows(jdbc).followup(first.attemptId, first.answerId)
        // 앞선 정정이 있으면 지금 보이는 결과는 정정 결과 (정정 직전 결과와 같은 규칙)
        UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "ADMIN", setOf(student.toString()), null))
        service.correct(first.judgmentId, CorrectionCommand(UUID.randomUUID(), "규칙 판정 오류", JudgmentResult.RETHINK, UUID.randomUUID()), UUID.randomUUID())

        // 보호자 범위에는 다른 자녀도 있음
        UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "PARENT", setOf(UUID.randomUUID().toString(), student.toString()), null))
        assertEquals(
            SupportTarget(student, first.attemptId, first.judgmentId, JudgmentResult.RETHINK),
            service.supportTarget(SupportTargetType.JUDGMENT, first.judgmentId),
        )
        assertEquals(SupportTarget(student, first.attemptId, first.judgmentId, null), service.supportTarget(SupportTargetType.FOLLOWUP, followupId))
        assertEquals(SupportTarget(student, first.attemptId, null, null), service.supportTarget(SupportTargetType.ATTEMPT, first.attemptId))
    }

    @Test
    fun `판정이 끝나기 전이면 previousResult 없음`() {
        val pending = submit()
        UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "STUDENT", setOf(student.toString()), null))

        assertEquals(
            SupportTarget(student, pending.attemptId, pending.judgmentId, null),
            service.supportTarget(SupportTargetType.JUDGMENT, pending.judgmentId),
        )
    }

    @Test
    fun `대상이 없으면 404, 대상 학생이 범위 밖이면 403`() {
        val done = submit()
        TestRows(jdbc).judged(done.answerId)
        val followupId = TestRows(jdbc).followup(done.attemptId, done.answerId)
        val targets = mapOf(SupportTargetType.JUDGMENT to done.judgmentId, SupportTargetType.FOLLOWUP to followupId, SupportTargetType.ATTEMPT to done.attemptId)

        UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "PARENT", setOf(UUID.randomUUID().toString()), null))
        val outside = targets.map { (type, id) -> assertThrows<BusinessException> { service.supportTarget(type, id) } }
        val missing = targets.keys.map { type -> assertThrows<BusinessException> { service.supportTarget(type, UUID.randomUUID()) } }
        val missingOriginal = assertThrows<BusinessException> { service.supportOriginal(UUID.randomUUID()) }
        UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "ADMIN", setOf(UUID.randomUUID().toString()), null))
        val outsideOriginal = assertThrows<BusinessException> { service.supportOriginal(done.attemptId) }

        assertEquals(List(3) { 403 to "FORBIDDEN" }, outside.map { it.status.value() to it.code })
        assertEquals(List(4) { 404 to "NOT_FOUND" }, (missing + missingOriginal).map { it.status.value() to it.code })
        assertEquals(403 to "FORBIDDEN", outsideOriginal.status.value() to outsideOriginal.code)
    }

    @Test
    fun `원문은 답변 버전 순 원문·피드백만, 초안·메모 없음, 피드백 판정에 판정 ID`() {
        val first = submit()
        TestRows(jdbc).judged(first.answerId, result = "PARTIAL")
        val followupId = TestRows(jdbc).followup(first.attemptId, first.answerId)
        val second = submit(first.attemptId, followupId, "두 번째 답")
        jdbc.update(
            "UPDATE attempt_draft SET content = CAST(? AS jsonb) WHERE attempt_id = ?",
            """{"answer":{"inputType":"NARRATIVE","text":"아직 안 낸 초안"},"memo":"혼자 쓴 메모"}""", first.attemptId,
        )

        UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "ADMIN", setOf(student.toString()), null))
        val original = service.supportOriginal(first.attemptId)

        assertEquals(student, original.studentId)
        assertEquals(listOf(first.answerId to 1, second.answerId to 2), original.answers.map { it.answerId to it.version })
        assertEquals(listOf("첫 답", "두 번째 답"), original.answers.map { it.text })
        assertEquals(first.judgmentId, original.answers[0].feedback.judgment?.judgmentId)
        assertEquals(JudgmentResult.PARTIAL, original.answers[0].feedback.judgment?.result)
        assertEquals(ProcessStatus.PENDING, original.answers[1].feedback.status)
        // 응답 칸은 정확히 이것만 (core도 이 네 칸만 골라 씀)
        val tree = json.valueToTree<com.fasterxml.jackson.databind.JsonNode>(original)
        assertEquals(setOf("studentId", "attemptId", "answers"), tree.fieldNames().asSequence().toSet())
        assertEquals(setOf("answerId", "version", "text", "feedback"), tree["answers"][0].fieldNames().asSequence().toSet())
        val body = json.writeValueAsString(original)
        assertFalse("혼자 쓴 메모" in body || "아직 안 낸 초안" in body || "memo" in body || "draft" in body)
    }

    private data class Submitted(val attemptId: UUID, val answerId: UUID, val judgmentId: UUID)

    /** 서술 답변을 제출(판정 PENDING). attemptId가 없으면 새 미션·시도 */
    private fun submit(attemptId: UUID? = null, followupId: UUID? = null, text: String = "첫 답"): Submitted {
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        val attempt = attemptId ?: TestRows(jdbc).let { rows ->
            val mission = rows.mission()
            rows.rubric(mission)
            attemptService.start(student, mission.id, 3, demo = false).attempt.id
        }
        val answer = answerService.submit(attempt, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = text), false, followupId))
        UserContextHolder.clear()
        val judgmentId = jdbc.queryForObject("SELECT id FROM judgment WHERE answer_id = ?", UUID::class.java, answer.id)!!
        return Submitted(attempt, answer.id, judgmentId)
    }
}
