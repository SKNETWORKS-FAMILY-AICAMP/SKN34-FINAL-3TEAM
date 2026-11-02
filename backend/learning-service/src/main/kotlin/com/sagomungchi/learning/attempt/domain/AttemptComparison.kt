package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import java.time.Instant
import java.util.UUID

data class ComparisonAnswer(val answerId: UUID, val version: Int, val text: String?, val content: Map<String, Any?>)
data class ComparisonMission(val title: String, val question: String, val inputType: String,
    val choices: List<com.sagomungchi.learning.mission.domain.Choice>,
    val categories: List<com.sagomungchi.learning.mission.domain.Category>, val answerUnit: String?)

data class ComparisonSnapshot(val attemptId: UUID, val finishedAt: Instant, val answers: List<ComparisonAnswer>,
    val judgment: JudgmentResult?, val elements: List<ElementView>, val mission: ComparisonMission)
enum class ComparisonState { NO_PREVIOUS, COMPARABLE, CRITERIA_CHANGED }
enum class ElementChange { ADDED, RETAINED, NOT_CONFIRMED, NOT_CONFIRMED_NOW }
data class ComparedElement(val elementId: UUID, val label: String, val previousSatisfied: Boolean,
    val currentSatisfied: Boolean, val change: ElementChange)
data class AttemptComparison(val attemptId: UUID, val state: ComparisonState,
    val previous: ComparisonSnapshot?, val current: ComparisonSnapshot, val elements: List<ComparedElement>) {
    companion object {
        /** 같은 기준표의 확인 항목만 비교한다. 개수 차이를 능력 점수로 해석하지 않는다. */
        fun of(current: ComparisonSnapshot, previous: ComparisonSnapshot?, sameCriteria: Boolean): AttemptComparison {
            val state = when { previous == null -> ComparisonState.NO_PREVIOUS
                !sameCriteria -> ComparisonState.CRITERIA_CHANGED
                else -> ComparisonState.COMPARABLE }
            val old = previous?.elements?.associateBy { it.elementId }.orEmpty()
            val changes = if (state != ComparisonState.COMPARABLE) emptyList() else current.elements.map { now ->
                val before = old[now.elementId]?.satisfied == true
                val change = when { before && now.satisfied -> ElementChange.RETAINED
                    now.satisfied -> ElementChange.ADDED
                    before -> ElementChange.NOT_CONFIRMED_NOW
                    else -> ElementChange.NOT_CONFIRMED }
                ComparedElement(now.elementId, now.label, before, now.satisfied, change)
            }
            return AttemptComparison(current.attemptId, state, previous, current, changes)
        }
    }
}
