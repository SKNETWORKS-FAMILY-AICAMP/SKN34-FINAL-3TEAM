package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.RubricElement
import java.time.Instant

/**
 * 마무리 뒤 공개 (FN-LRN-11, api-spec 3.8). reveal은 시도에 고정된 기준표 버전의 예시 답(닫힌 문제는 정답과 해설),
 * checklist는 기준표 요소마다 한 줄
 */
data class FinishResult(
    val finishedAt: Instant,
    val reveal: String?,
    val revealKind: RevealKind,
    val checklist: List<ElementView>,
)

/** 닫힌 문제(정답이 정해진 고르기·순서·분류·풀이 단계)는 정답, 열린 문제(서술·논술)는 예시 답 (FN-LRN-11) */
enum class RevealKind {
    ANSWER,
    EXAMPLE,
    ;

    companion object {
        fun of(inputType: InputType): RevealKind = when (inputType) {
            InputType.NARRATIVE, InputType.ESSAY -> EXAMPLE
            else -> ANSWER
        }
    }
}

object Checklist {
    /**
     * 기준표 요소마다 한 줄 (FN-LRN-11, api-spec 3.8): 이 시도의 처리 완료 판정 중 원문 구절과 함께 충족된 적이 있으면 체크하고
     * 가장 최근 구절을 표시. 보완 답변의 판정은 그 답변 글만 보므로 앞 답변에서 확인된 요소도 합침.
     * judged는 답변 버전 순
     */
    fun of(elements: List<RubricElement>, judged: List<ElementView>): List<ElementView> {
        val confirmed = judged.filter { it.satisfied && it.quote != null }.associateBy { it.elementId }
        return elements.map { element ->
            confirmed[element.id]?.copy(label = element.label) ?: ElementView(element.id, element.label, false, null, null)
        }
    }
}
