package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning.mission.domain.HintQuestion
import java.util.UUID

/** 생각 열기 열람 결과. question.seq는 이번에 연 질문 순서(1부터), total은 미션의 질문 수 */
data class HintOpened(
    val question: HintQuestion,
    val total: Int,
) {
    companion object {
        /** 아직 열지 않은 질문을 seq 순으로, 다 열었으면 마지막 질문. 질문이 없으면 부르지 않음 */
        fun next(questions: List<HintQuestion>, openedIds: Set<UUID>): HintOpened {
            val ordered = questions.sortedBy { it.seq }
            val question = ordered.firstOrNull { it.id !in openedIds } ?: ordered.last()
            return HintOpened(question, ordered.size)
        }
    }
}
