package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.domain.ComparisonState
import com.sagomungchi.learning.attempt.domain.Difficulty
import com.sagomungchi.learning.attempt.domain.ElementChange
import com.sagomungchi.learning.attempt.domain.Reflection
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
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class AttemptComparisonIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var attempts: AttemptService
    @Autowired lateinit var answers: AnswerService
    @Autowired lateinit var jdbc: JdbcTemplate
    private val student = UUID.randomUUID()
    private lateinit var rows: TestRows
    @BeforeEach fun prepare() {
        rows = TestRows(jdbc)
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
    }
    @AfterEach fun clear() = UserContextHolder.clear()
    private fun submit(id: UUID, text: String, elements: List<Pair<UUID, String?>>) {
        val answer = answers.submit(id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = text), false, null))
        rows.judged(answer.id, elements)
    }

    @Test fun `재시도는 새 시도를 만들고 직전 원문 판정 피드백을 보존한 채 변화 조회`() {
        val mission = rows.mission()
        val elements = rows.rubric(mission, listOf("까닭", "다른 생각"))
        val previous = attempts.start(student, mission.id, 3, false).attempt
        submit(previous.id, "예전 까닭", listOf(elements[0] to "예전 까닭", elements[1] to null))
        attempts.finish(previous.id)
        attempts.saveReflection(previous.id, Reflection(Difficulty.NORMAL, null))
        val before = attempts.get(previous.id)
        val current = attempts.start(student, mission.id, 3, false).attempt
        assertNotEquals(previous.id, current.id)
        submit(current.id, "새 까닭과 다른 생각", listOf(elements[0] to "새 까닭", elements[1] to "다른 생각"))
        attempts.finish(current.id)
        val result = attempts.comparison(current.id)
        assertEquals(ComparisonState.COMPARABLE, result.state)
        assertEquals(previous.id, result.previous!!.attemptId)
        assertEquals(listOf(ElementChange.RETAINED, ElementChange.ADDED), result.elements.map { it.change })
        assertEquals(before, attempts.get(previous.id))
        assertEquals("예전 까닭", result.previous!!.answers.single().text)
        assertEquals("새 까닭과 다른 생각", result.current.answers.single().text)
    }

    @Test fun `마무리 전에는 비교를 공개하지 않고 첫 마무리는 이전 결과 없음`() {
        val mission = rows.mission(); val elements = rows.rubric(mission, listOf("까닭"))
        val attempt = attempts.start(student, mission.id, 3, false).attempt
        assertEquals("REVEAL_CONDITION_UNMET", assertThrows<BusinessException> { attempts.comparison(attempt.id) }.code)
        submit(attempt.id, "합성 까닭", listOf(elements[0] to "합성 까닭"))
        attempts.finish(attempt.id)
        assertEquals(ComparisonState.NO_PREVIOUS, attempts.comparison(attempt.id).state)
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(UUID.randomUUID().toString()), null))
        assertEquals(HttpStatus.FORBIDDEN, assertThrows<BusinessException> { attempts.comparison(attempt.id) }.status)
    }

    @Test fun `현재 시작 뒤 마무리된 시도는 기준으로 삼지 않음`() {
        val mission = rows.mission(); val elements = rows.rubric(mission, listOf("까닭"))
        val old = attempts.start(student, mission.id, 3, false).attempt
        submit(old.id, "이전", listOf(elements[0] to "이전")); attempts.finish(old.id)
        attempts.saveReflection(old.id, Reflection(Difficulty.NORMAL, null))
        val current = attempts.start(student, mission.id, 3, false).attempt
        submit(current.id, "현재", listOf(elements[0] to "현재")); attempts.finish(current.id)
        jdbc.update("UPDATE attempt SET finished_at = ?, completed_at = ? WHERE id = ?",
            java.sql.Timestamp.from(current.startedAt.plusSeconds(1)), java.sql.Timestamp.from(current.startedAt.plusSeconds(1)), old.id)
        val result = attempts.comparison(current.id)
        assertEquals(ComparisonState.NO_PREVIOUS, result.state)
        assertTrue(result.elements.isEmpty())
    }
}
