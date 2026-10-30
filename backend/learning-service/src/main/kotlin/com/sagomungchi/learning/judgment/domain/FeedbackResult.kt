package com.sagomungchi.learning.judgment.domain

import java.util.UUID

/**
 * 피드백 결과 (api-spec 3.2 `result` 이벤트). DONE이면 판정·되묻기·버전, 처리 중이면 status만 (api-spec 1.4).
 * nextActions는 지금 할 수 있는 행동이라 같은 판정이라도 되묻기에 답했거나 마무리했으면 달라짐
 */
data class FeedbackResult(
    val status: ProcessStatus,
    val judgment: JudgmentView?,
    val followup: FollowupView?,
    val nextActions: List<NextAction>,
    val versions: Versions?,
) {
    companion object {
        fun inProgress(status: ProcessStatus) = FeedbackResult(status, null, null, emptyList(), null)
    }
}

/** judgmentId는 신고(targetType JUDGMENT)·정정 대상 ID (#146) */
data class JudgmentView(
    val judgmentId: UUID,
    val result: JudgmentResult,
    val trial: Boolean,
    val elements: List<ElementView>,
    val heldReason: String?,
)

/** 요소 판정. elementId는 rubric_element.id, quote는 학생 답 원문 구절 또는 고른 답 */
data class ElementView(
    val elementId: UUID,
    val label: String,
    val satisfied: Boolean,
    val quote: String?,
    val sourceType: ElementSource?,
)

data class FollowupView(
    val followupId: UUID,
    val type: FollowupType,
    val question: String,
    val source: FollowupSource,
)

/** api-spec 1.6. mission·rubric은 "미션 code@버전", model·prompt는 판정 값(규칙 판정이면 없음) */
data class Versions(
    val mission: String,
    val rubric: String,
    val model: String?,
    val prompt: String?,
)
