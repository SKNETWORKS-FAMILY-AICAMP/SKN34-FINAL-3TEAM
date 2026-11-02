package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import org.junit.jupiter.api.Test
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AttemptComparisonTest {
    private val first = UUID.randomUUID()
    private val second = UUID.randomUUID()
    private fun snapshot(firstSatisfied: Boolean, secondSatisfied: Boolean) = ComparisonSnapshot(
        UUID.randomUUID(), Instant.parse("2026-11-01T00:00:00Z"),
        listOf(ComparisonAnswer(UUID.randomUUID(), 1, "합성 원문", mapOf("text" to "합성 원문"))),
        JudgmentResult.PARTIAL,
        listOf(ElementView(first, "까닭", firstSatisfied, if (firstSatisfied) "합성" else null, null),
            ElementView(second, "다른 생각", secondSatisfied, if (secondSatisfied) "원문" else null, null)),
        ComparisonMission("합성 미션", "질문", "NARRATIVE", emptyList(), emptyList(), null),
    )

    @Test fun `이전 결과가 없으면 점수나 변화 항목을 만들어내지 않음`() {
        val result = AttemptComparison.of(snapshot(true, false), null, false)
        assertEquals(ComparisonState.NO_PREVIOUS, result.state)
        assertTrue(result.elements.isEmpty())
    }

    @Test fun `같은 기준의 추가 확인과 이번에 확인하지 못한 항목을 구분`() {
        val before = snapshot(false, true)
        val current = snapshot(true, false)
        val result = AttemptComparison.of(current, before, true)
        assertEquals(ComparisonState.COMPARABLE, result.state)
        assertEquals(listOf(ElementChange.ADDED, ElementChange.NOT_CONFIRMED_NOW), result.elements.map { it.change })
        assertEquals(before, result.previous)
        assertEquals(current, result.current)
    }

    @Test fun `유지와 미확인 항목, 판정 보류 원문을 보존`() {
        val before = snapshot(true, false)
        val current = snapshot(true, false).copy(judgment = JudgmentResult.HELD)
        val result = AttemptComparison.of(current, before, true)
        assertEquals(listOf(ElementChange.RETAINED, ElementChange.NOT_CONFIRMED), result.elements.map { it.change })
        assertEquals(JudgmentResult.HELD, result.current.judgment)
        assertEquals("합성 원문", result.previous!!.answers.single().text)
    }

    @Test fun `기준 버전 변경은 같은 항목 이름이어도 충족 변화를 직접 비교하지 않음`() {
        val result = AttemptComparison.of(snapshot(true, true), snapshot(false, false), false)
        assertEquals(ComparisonState.CRITERIA_CHANGED, result.state)
        assertTrue(result.elements.isEmpty())
    }
}
