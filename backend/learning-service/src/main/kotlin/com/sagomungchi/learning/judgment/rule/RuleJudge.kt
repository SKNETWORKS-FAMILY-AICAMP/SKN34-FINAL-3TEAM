package com.sagomungchi.learning.judgment.rule

import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.InputType

/**
 * 정답 키로 판정하는 규칙 (class-diagram 4.2, FN-JDG-01·02). 같으면 CORRECT, 아니면 RETHINK.
 * 정답 키가 없는 미션은 공개 검사에서 막히므로 없으면 오류
 */
interface RuleJudge {
    fun supports(inputType: InputType): Boolean

    fun judge(answer: AnswerContent, answerKey: AnswerKey): Judged
}

internal fun missingKey(field: String): Nothing = error("정답 키에 $field 없음")
