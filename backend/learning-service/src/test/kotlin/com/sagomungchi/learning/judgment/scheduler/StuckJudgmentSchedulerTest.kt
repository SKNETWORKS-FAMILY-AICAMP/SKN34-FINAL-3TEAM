package com.sagomungchi.learning.judgment.scheduler

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.service.JudgmentService
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.extension.ExtendWith
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.system.CapturedOutput
import org.springframework.boot.test.system.OutputCaptureExtension
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** #241 고착 RUNNING 판정 주기 탐지: 켜져 있으면 탐지, 끄면(app.judgment.stuck-detection-enabled=false) 아무것도 바꾸지 않음 */
@ExtendWith(OutputCaptureExtension::class)
class StuckJudgmentSchedulerTest : PostgresRepositoryTest() {
    @Autowired lateinit var scheduler: StuckJudgmentScheduler
    @Autowired lateinit var service: JudgmentService
    @Autowired lateinit var properties: AppProperties
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `켜져 있으면 리스가 끝난 RUNNING을 FAILED로`() {
        val answerId = stuck()

        scheduler.detect()

        assertEquals("FAILED", status(answerId))
    }

    @Test
    fun `처리 로그에는 건수와 답변 ID만 남고 학생 원문은 없음`(output: CapturedOutput) {
        val answerId = stuck()

        scheduler.detect()

        assertTrue("고착 판정 FAILED 처리:" in output.out && answerId.toString() in output.out)
        assertFalse(TEXT in output.out)
    }

    @Test
    fun `끄면 탐지하지 않음`() {
        val answerId = stuck()
        val off = properties.copy(judgment = AppProperties.Judgment(stuckDetectionEnabled = false))

        StuckJudgmentScheduler(service, off).detect()

        assertEquals("RUNNING", status(answerId))
    }

    /** 리스가 1분 전에 끝난 RUNNING 판정의 답변 ID */
    private fun stuck(): UUID {
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        rows.rubric(mission)
        val student = UUID.randomUUID()
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        val attempt = attemptService.start(student, mission.id, 3, demo = false).attempt
        val answer = answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = TEXT), false, null))
        jdbc.update("UPDATE judgment SET process_status = 'RUNNING', lease_until = now() - interval '1 minute' WHERE answer_id = ?", answer.id)
        return answer.id
    }

    private fun status(answerId: UUID) =
        jdbc.queryForObject("SELECT process_status FROM judgment WHERE answer_id = ?", String::class.java, answerId)

    companion object {
        /** 로그에 나오면 안 되는 학생 원문 */
        private const val TEXT = "놀이터에서 친구와 그네를 탔다"
    }
}
