package com.sagomungchi.learning.answer.domain

import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** 생각·작성 시간 저장 규칙 (P28, api-spec 3.1, #801) */
class AnswerTimeTest {
    private val written = listOf(InputType.NARRATIVE, InputType.SOLUTION_STEPS, InputType.ESSAY)

    @Test
    fun `글 입력 방식은 0초부터 24시간까지 그대로`() {
        written.forEach { type ->
            assertEquals(AnswerTime(95, 240), AnswerTime.of(95, 240, type, dictatedByGuardian = false))
            assertEquals(AnswerTime(0, 0), AnswerTime.of(0, 0, type, dictatedByGuardian = false))
            assertEquals(AnswerTime(86_400, 86_400), AnswerTime.of(86_400, 86_400, type, dictatedByGuardian = false))
        }
    }

    @Test
    fun `하나라도 없거나 범위 밖이면 둘 다 없음`() {
        listOf(null to 240L, 95L to null, null to null, -1L to 240L, 95L to -1L, 86_401L to 240L, 95L to 86_401L, Long.MAX_VALUE to 0L)
            .forEach { (thinking, writing) -> assertNull(AnswerTime.of(thinking, writing, InputType.NARRATIVE, false), "$thinking, $writing") }
    }

    @Test
    fun `고르기 방식과 보호자 받아쓰기는 값이 와도 없음`() {
        listOf(InputType.CHOICE, InputType.ORDERING, InputType.CLASSIFICATION).forEach { assertNull(AnswerTime.of(5, 1, it, false), it.name) }
        written.forEach { assertNull(AnswerTime.of(95, 240, it, dictatedByGuardian = true), it.name) }
    }
}
