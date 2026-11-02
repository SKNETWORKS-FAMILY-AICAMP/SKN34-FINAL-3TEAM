package com.sagomungchi.learning.mission.domain

import java.util.UUID

/**
 * 판정용 기준표 (ERD rubric_version·rubric_element). 정답 키·예시 답이 있어 학생 응답에 담지 않음 (FN-LRN-03).
 * missionLabel·rubricLabel은 판정 응답 versions 표기 "미션 code@버전" (api-spec 1.6)
 */
data class Rubric(
    val rubricVersionId: UUID,
    val missionLabel: String,
    val rubricLabel: String,
    val answerKey: AnswerKey?,
    val exampleAnswer: String?,
    val forbiddenTerms: List<String>,
    val elements: List<RubricElement>,
) {
    /** ai가 판정하는 요소. 최종 답 요소는 정답 키로 정하므로 뺌 (FN-JDG-02, #79) */
    val aiElements: List<RubricElement> get() = elements.filterNot { it.code == RubricElement.FINAL_ANSWER }

    /** 풀이 단계의 최종 답 요소: 수학 동치 규칙 결과로 충족을 정해 체크리스트에 보임 */
    val finalAnswerElements: List<RubricElement> get() = elements.filter { it.code == RubricElement.FINAL_ANSWER }
}

/** 기준표 요소. goodThought는 "들어가면 좋은 생각"(필수 아님), judgeVerified는 사람 검증 통과 (P11) */
data class RubricElement(
    val id: UUID,
    val code: String,
    val label: String,
    val description: String?,
    val points: Int,
    val commonErrors: List<String>,
    val goodThought: Boolean,
    val judgeVerified: Boolean,
) {
    companion object {
        /** 수학 최종 답 요소의 예약 코드 (ERD 4.1 rubric_element.code, #79) */
        const val FINAL_ANSWER = "FINAL_ANSWER"
    }
}

/**
 * 정답 키 (rubric_version.answer_key). 고르기 `choiceIds` 1개, 순서 `choiceIds` 정답 순서,
 * 분류 `assignments`(categoryId는 미션 categories), 수학 `finalAnswer`(수만, 단위는 미션 answerUnit으로 보여 주고 비교하지 않음)
 */
data class AnswerKey(
    val choiceIds: List<String>? = null,
    val finalAnswer: String? = null,
    val assignments: List<KeyAssignment>? = null,
)

data class KeyAssignment(val choiceId: String, val categoryId: String)
