package com.sagomungchi.learning.judgment.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.judgment.domain.JudgedBy
import com.sagomungchi.learning.judgment.domain.JudgmentMethod
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.judgment.domain.JudgmentElement
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class JudgmentServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: JudgmentService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `리스가 끝나 다른 요청이 다시 가져가면 늦게 끝난 처리는 저장도 실패 기록도 못 함 (state-diagram 3·3)`() {
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        val element = rows.rubric(mission).single()
        val student = UUID.randomUUID()
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
        val answer = answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "답"), false, null))
        val judged = Judged(
            JudgmentResult.PARTIAL, null,
            listOf(JudgmentElement(element, "답", verified = true, sourceType = ElementSource.AI_OBSERVATION).satisfy()),
            JudgedBy(JudgmentMethod.LLM, trial = true, model = "m", prompt = "p"),
        )
        val now = Instant.now().truncatedTo(ChronoUnit.MICROS)

        val first = assertIs<AcquireResult.Acquired>(service.acquire(answer.id, now)).judgment
        assertEquals(AcquireResult.Busy(ProcessStatus.RUNNING), service.acquire(answer.id, now.plusSeconds(1)))
        val second = assertIs<AcquireResult.Acquired>(service.acquire(answer.id, now.plus(Judgment.LEASE).plusSeconds(1))).judgment

        assertFalse(service.saveResult(first, judged, null))
        assertFalse(service.markFailed(first, "AI_TIMEOUT"))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM judgment_element WHERE judgment_id = ?", Int::class.java, first.id))
        assertTrue(service.saveResult(second, judged, null))
        assertEquals(AcquireResult.Busy(ProcessStatus.DONE), service.acquire(answer.id, now.plus(Judgment.LEASE.multipliedBy(3))))
        assertEquals(listOf("DONE", 0), jdbc.queryForMap("SELECT process_status, retry_count FROM judgment WHERE id = ?", first.id).values.toList())
    }
}
