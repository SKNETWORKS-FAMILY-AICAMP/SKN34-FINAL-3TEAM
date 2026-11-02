package com.sagomungchi.learning.judgment.domain

import java.util.UUID

enum class FollowupType { ONE_STEP_MORE, TELL_MORE, LOOK_AGAIN }

/** 되묻기 질문 출처. 재생성까지 유출 검사에 실패하면 질문 은행(BANK, P16) */
enum class FollowupSource { LLM, LLM_RETRY, BANK }

/**
 * 되묻기 (ERD 4.2 followup, class-diagram 4.2). 질문 은행 질문이면 bankQuestionId가 있고
 * 모델·프롬프트 버전은 없음 (ERD CHECK ck_followup_bank_source)
 */
data class Followup(
    val attemptId: UUID,
    val type: FollowupType,
    val question: String,
    val source: FollowupSource,
    val leakCheckPassed: Boolean,
    val bankQuestionId: UUID?,
    val modelVersion: String?,
    val promptVersion: String?,
) {
    init {
        require((source == FollowupSource.BANK) == (bankQuestionId != null)) { "질문 은행 질문만 bankQuestionId" }
    }
}

/** 질문 은행의 중립 질문 (P16) */
data class BankQuestion(val id: UUID, val question: String)
