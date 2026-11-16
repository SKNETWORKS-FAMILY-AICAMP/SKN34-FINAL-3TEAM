package com.sagomungchi.learning._common.web

import com.fasterxml.jackson.annotation.JsonInclude
import com.fasterxml.jackson.annotation.JsonRawValue
import java.util.UUID

/**
 * 피드백 결과 (api-spec 3.2 `result` 이벤트). DONE이면 판정·되묻기·버전, 처리 중이면 status만 (api-spec 1.4).
 * nextActions는 지금 할 수 있는 행동이라 같은 판정이라도 되묻기에 답했거나 마무리했으면 달라짐
 */
data class FeedbackResponse(
    val status: String,
    val judgment: JudgmentResponse?,
    val followup: FollowupResponse?,
    val nextActions: List<String>,
    val versions: FeedbackVersions?,
) {
    companion object {
        fun inProgress(status: String) = FeedbackResponse(status, null, null, emptyList(), null)
    }
}

/**
 * judgmentId는 신고(targetType JUDGMENT)·정정 대상 ID (#146).
 * corrected는 정정이 있으면 true. 정정은 결과만 바꾸고 elements는 원판정 그대로라 report 요소 지표에서 뺌 (FN-RPT-05, #244)
 * modelScores는 report 집계 입력(includeModelScores, #478)에서만 채움: 저장 JSON 원문, M2를 부르지 않았으면 "null".
 * 그 밖의 응답(학생 시도 상세·학부모·ai)은 Kotlin null이라 키 자체가 없음 (api-spec 4.1.1)
 */
data class JudgmentResponse(
    val judgmentId: UUID,
    val result: String,
    val trial: Boolean,
    val elements: List<ElementResponse>,
    val heldReason: String?,
    val corrected: Boolean = false,
    @get:JsonRawValue @get:JsonInclude(JsonInclude.Include.NON_NULL) val modelScores: String? = null,
    @get:JsonInclude(JsonInclude.Include.NON_EMPTY) val m2Notices: List<String> = emptyList(),
)

/**
 * 요소 판정. elementId는 rubric_element.id, quote는 학생 답 원문 구절 또는 고른 답.
 * code·goodThought는 report 요소 지표용 (FN 1.5 표준 요소, FN-RPT-05, #262). 화면 표시용 아님
 */
data class ElementResponse(
    val elementId: UUID,
    val label: String,
    val code: String,
    val goodThought: Boolean,
    val satisfied: Boolean,
    val quote: String?,
    val sourceType: String?,
)

data class FollowupResponse(
    val followupId: UUID,
    val type: String,
    val question: String,
    val source: String,
)

/** api-spec 1.6. mission·rubric은 "미션 code@버전", model·prompt는 판정 값(규칙 판정이면 없음) */
data class FeedbackVersions(
    val mission: String,
    val rubric: String,
    val model: String?,
    val prompt: String?,
)
