package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.RubricElement
import org.junit.jupiter.api.Test
import java.util.UUID
import kotlin.test.assertEquals

class ChecklistTest {
    private fun element(label: String) = RubricElement(UUID.randomUUID(), label, label, null, 1, emptyList(), goodThought = false, judgeVerified = false)

    @Test
    fun `기준표 순서대로 요소마다 한 줄, 충족과 원문 구절이 모두 있어야 체크하고 가장 최근 구절 (api-spec 3·8)`() {
        val (claim, reason, other) = listOf(element("주장"), element("근거"), element("다른 관점"))
        val judged = listOf(
            ElementView(reason.id, "근거", true, "처음 구절", ElementSource.AI_OBSERVATION),
            ElementView(other.id, "다른 관점", true, null, ElementSource.AI_OBSERVATION),
            ElementView(claim.id, "주장", false, null, null),
            ElementView(reason.id, "근거", true, "나중 구절", ElementSource.AI_OBSERVATION),
            ElementView(reason.id, "근거", false, null, null),
        )

        assertEquals(
            listOf(
                ElementView(claim.id, "주장", false, null, null),
                ElementView(reason.id, "근거", true, "나중 구절", ElementSource.AI_OBSERVATION),
                ElementView(other.id, "다른 관점", false, null, null),
            ),
            Checklist.of(listOf(claim, reason, other), judged),
        )
    }

    @Test
    fun `닫힌 문제(고르기·순서·분류·풀이 단계)는 정답, 서술·논술은 예시 답 (FN-LRN-11)`() {
        val expected = mapOf(
            InputType.CHOICE to RevealKind.ANSWER,
            InputType.ORDERING to RevealKind.ANSWER,
            InputType.CLASSIFICATION to RevealKind.ANSWER,
            InputType.SOLUTION_STEPS to RevealKind.ANSWER,
            InputType.NARRATIVE to RevealKind.EXAMPLE,
            InputType.ESSAY to RevealKind.EXAMPLE,
        )
        assertEquals(expected, InputType.entries.associateWith { RevealKind.of(it) })
    }
}
