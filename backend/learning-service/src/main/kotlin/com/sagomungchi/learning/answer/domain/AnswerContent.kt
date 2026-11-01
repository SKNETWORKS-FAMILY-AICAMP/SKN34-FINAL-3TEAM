package com.sagomungchi.learning.answer.domain

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionView

/**
 * 입력 방식별 제출 내용 (api-spec 3.1·3.8). 저장할 때는 그 입력 방식에 쓰는 필드만 남김 (only).
 * 메모는 제출에 포함하지 않음 (P05).
 */
data class AnswerContent(
    val text: String? = null,
    val finalAnswer: String? = null,
    val steps: List<String>? = null,
    val essay: Essay? = null,
    val choiceIds: List<String>? = null,
    val assignments: List<Assignment>? = null,
) {
    /** 이 입력 방식에 쓰는 필드만 */
    fun only(inputType: InputType) = when (inputType) {
        InputType.NARRATIVE -> AnswerContent(text = text)
        InputType.SOLUTION_STEPS -> AnswerContent(finalAnswer = finalAnswer, steps = steps)
        InputType.ESSAY -> AnswerContent(essay = essay)
        InputType.CHOICE, InputType.ORDERING -> AnswerContent(choiceIds = choiceIds)
        InputType.CLASSIFICATION -> AnswerContent(assignments = assignments)
    }

    /**
     * 필요한 선택·입력이 빠지면 422 ANSWER_INCOMPLETE (api-spec 1.3, FN-LRN-04·05).
     * 규칙은 프론트 validateAnswer와 같음. 분류는 미션 그룹(categories)에 있는 그룹에만 넣어야 함 (#79)
     */
    fun requireComplete(inputType: InputType, mission: MissionView) {
        val choiceIds = mission.choices.map { it.id }
        val message = when (inputType) {
            InputType.NARRATIVE ->
                "내 생각을 먼저 적어 주세요.".takeIf { text.isNullOrBlank() }
            InputType.SOLUTION_STEPS ->
                "답과 풀이 과정을 함께 남겨 주세요."
                    .takeIf { finalAnswer.isNullOrBlank() || steps.orEmpty().none { it.isNotBlank() } }
            InputType.ESSAY ->
                "주장, 까닭 두 가지, 다른 의견에 대한 답을 채워 주세요."
                    .takeIf { essay == null || !essay.allFilled() }
            InputType.CHOICE ->
                "답을 하나 골라 주세요."
                    .takeIf { choiceIds.isEmpty() || this.choiceIds?.size != 1 || this.choiceIds.single() !in choiceIds }
            InputType.ORDERING ->
                "모든 항목의 순서를 정해 주세요."
                    .takeIf { choiceIds.isEmpty() || this.choiceIds.orEmpty().sorted() != choiceIds.sorted() }
            InputType.CLASSIFICATION -> {
                val assigned = assignments.orEmpty()
                val categoryIds = mission.categories.map { it.id }.toSet()
                "모든 항목을 알맞은 그룹에 한 번씩 넣어 주세요.".takeIf {
                    choiceIds.isEmpty() ||
                        assigned.map { it.choiceId }.sorted() != choiceIds.sorted() ||
                        assigned.any { it.categoryId !in categoryIds }
                }
            }
        }
        if (message != null) throw BusinessException(ErrorKind.UNPROCESSABLE, "ANSWER_INCOMPLETE", "답변 미완성", message)
    }

    /**
     * 판정 인용 대조용 원문 (ERD answer.plain_text, #25 판정 입력). 논술·풀이 단계는 미션 입력 틀의 칸 이름을 붙임.
     * 고르기·순서는 선택지 이름을 순서대로, 분류는 "선택지 이름: 그룹 이름", 풀이 최종 답에는 미션 답 단위를 붙임
     */
    fun plainText(inputType: InputType, mission: MissionView): String {
        val labels = mission.choices.associate { it.id to it.label }
        return when (inputType) {
            InputType.NARRATIVE -> text.orEmpty()
            InputType.SOLUTION_STEPS -> {
                val stepLines = steps.orEmpty().mapIndexedNotNull { index, step ->
                    step.takeIf { it.isNotBlank() }?.let { "${mission.inputTemplate.getOrElse(index) { "단계 ${index + 1}" }}: $it" }
                }
                val answer = finalAnswer.orEmpty().trim()
                val unit = mission.answerUnit?.takeUnless { answer.endsWith(it) }
                (stepLines + "최종 답: ${listOfNotNull(answer, unit).joinToString(" ")}").joinToString("\n")
            }
            InputType.ESSAY -> {
                val essay = checkNotNull(essay)
                val names = mission.inputTemplate.takeIf { it.size == ESSAY_FIELDS }
                    ?: listOf("주장", "까닭 1", "까닭 2", "반대 의견에 답하기")
                listOf(essay.claim, essay.reasons[0], essay.reasons[1], essay.rebuttal)
                    .mapIndexed { index, value -> "${names[index]}: $value" }
                    .joinToString("\n")
            }
            InputType.CHOICE, InputType.ORDERING -> choiceIds.orEmpty().joinToString(" → ") { labels[it] ?: it }
            InputType.CLASSIFICATION -> {
                val groups = mission.categories.associate { it.id to it.label }
                assignments.orEmpty().joinToString("\n") { "${labels[it.choiceId] ?: it.choiceId}: ${groups[it.categoryId] ?: it.categoryId}" }
            }
        }
    }

    companion object {
        private const val ESSAY_FIELDS = 4
    }
}

/** 논술 틀: 주장·까닭 2개·반대 의견에 답하기 (P03). 검사 함수를 is…로 지으면 Jackson이 저장할 값으로 씀 */
data class Essay(
    val claim: String,
    val reasons: List<String>,
    val rebuttal: String,
) {
    fun allFilled() = reasons.size == 2 && (listOf(claim, rebuttal) + reasons).all { it.isNotBlank() }
}

/** 분류: 선택지 하나를 그룹 하나에 */
data class Assignment(val choiceId: String, val categoryId: String)
