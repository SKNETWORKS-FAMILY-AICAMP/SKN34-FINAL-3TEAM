package com.sagomungchi.learning.judgment.domain

enum class JudgmentResult { CORRECT, PARTIAL, RETHINK, HELD }

/** 규칙 판정(고르기·수학 최종 답) 또는 LLM 근거 추출 (ERD judgment.method) */
enum class JudgmentMethod { RULE, LLM }

/** 근거 출처 (api-spec 1.5). 규칙 판정은 ANSWER_KEY, LLM 근거 구절은 AI_OBSERVATION (api-spec 3.2) */
enum class ElementSource { RECORD, RULE, ANSWER_KEY, AI_OBSERVATION }

/** 학생이 지금 할 수 있는 행동 (api-spec 2.2). FINISH는 "이대로 돌아보기" */
enum class NextAction { ANSWER_FOLLOWUP, FINISH }

/** 누가 어떻게 판정했는지 (ERD judgment.method·trial·model_version·prompt_version). 규칙 판정이면 모델·프롬프트 없음 */
data class JudgedBy(
    val method: JudgmentMethod,
    val trial: Boolean,
    val model: String?,
    val prompt: String?,
) {
    companion object {
        val RULE = JudgedBy(JudgmentMethod.RULE, trial = false, model = null, prompt = null)
    }
}

/**
 * 규칙·ai 판정 결과 (class-diagram 4.2 `RuleJudge.judge` 반환값, 저장 전).
 * 보류(HELD)면 사유가 꼭 있고 그 밖에는 없음 (ERD CHECK와 같은 규칙)
 */
data class Judged(
    val result: JudgmentResult,
    val heldReason: String?,
    val elements: List<JudgmentElement>,
    val by: JudgedBy,
) {
    init {
        require((result == JudgmentResult.HELD) == (heldReason != null)) { "보류 사유는 HELD일 때만" }
    }

    companion object {
        /** 규칙 판정: 정답 키와 같으면 CORRECT, 아니면 RETHINK (state-diagram 3.3). 요소는 FeedbackFacade가 채움 */
        fun byRule(correct: Boolean) =
            Judged(if (correct) JudgmentResult.CORRECT else JudgmentResult.RETHINK, null, emptyList(), JudgedBy.RULE)
    }
}
