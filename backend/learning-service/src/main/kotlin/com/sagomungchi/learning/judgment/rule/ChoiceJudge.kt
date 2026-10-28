package com.sagomungchi.learning.judgment.rule

import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.InputType
import org.springframework.stereotype.Component

/**
 * 고르기 활동 판정 (FN-JDG-01, FN-LRN-04 선택지·순서·분류). 고르기는 고른 1개, 순서는 순서까지,
 * 분류는 모든 선택지의 그룹이 정답 키와 같아야 정답
 */
@Component
class ChoiceJudge : RuleJudge {
    override fun supports(inputType: InputType) =
        inputType == InputType.CHOICE || inputType == InputType.ORDERING || inputType == InputType.CLASSIFICATION

    override fun judge(answer: AnswerContent, answerKey: AnswerKey): Judged {
        val correct = answer.assignments?.let { assigned ->
            val expected = answerKey.assignments ?: missingKey("assignments")
            assigned.map { it.choiceId to it.categoryId }.toSet() == expected.map { it.choiceId to it.categoryId }.toSet()
        } ?: (answer.choiceIds.orEmpty() == (answerKey.choiceIds ?: missingKey("choiceIds")))
        return Judged.byRule(correct)
    }
}
