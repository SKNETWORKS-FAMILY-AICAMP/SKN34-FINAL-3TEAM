package com.sagomungchi.learning.answer.domain

import com.sagomungchi.learning.mission.domain.InputType

/**
 * 답변 생각·작성 시간, 정수 초 (P28, api-spec 3.1, ERD 4.2). 웹이 재서 보내고 learning은 검사만 한다.
 * 두 값은 함께 있거나 함께 없음(null). 저장할 수 없는 값은 제출을 막지 않고 둘 다 버린다(#801)
 */
data class AnswerTime(val thinkingSeconds: Int, val writingSeconds: Int) {
    companion object {
        /** 24시간. 넘으면 탭을 열어 둔 채 둔 값으로 보고 저장하지 않음 (#800 확정) */
        const val MAX_SECONDS = 86_400L

        /** 글 입력 방식만 잰다. 고르기 방식은 첫 입력이 곧 제출이라 재지 않음 (#800 확정) */
        private val MEASURED = setOf(InputType.NARRATIVE, InputType.SOLUTION_STEPS, InputType.ESSAY)

        /**
         * 요청 값 → 저장 값. 고르기 방식·보호자 받아쓰기는 값이 와도 null,
         * 둘 중 하나라도 없거나 0 미만·24시간 초과면 둘 다 null
         */
        fun of(thinkingSeconds: Long?, writingSeconds: Long?, inputType: InputType, dictatedByGuardian: Boolean): AnswerTime? {
            if (inputType !in MEASURED || dictatedByGuardian) return null
            if (thinkingSeconds == null || writingSeconds == null) return null
            if (thinkingSeconds !in 0..MAX_SECONDS || writingSeconds !in 0..MAX_SECONDS) return null
            return AnswerTime(thinkingSeconds.toInt(), writingSeconds.toInt())
        }
    }
}
