package com.sagomungchi.learning.judgment.domain

import com.fasterxml.jackson.annotation.JsonInclude
import java.util.UUID

/** 신고·문의 대상 유형 (api-spec 4.1 `/internal/support/targets`, #146) */
enum class SupportTargetType { JUDGMENT, FOLLOWUP, ATTEMPT }

/**
 * 신고·문의 대상의 학생·시도 (#146). 원문 없음. judgmentId는 판정·되묻기, previousResult는 판정 DONE일 때만(지금 보이는 결과,
 * 정정 직전 결과와 같은 규칙). 없는 칸은 응답에서 뺌(core 계약은 선택 칸)
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
data class SupportTarget(
    val studentId: UUID,
    val attemptId: UUID,
    val judgmentId: UUID?,
    val previousResult: JudgmentResult?,
)

/** 관리자 원문 (#146): 답변 버전 순, 초안·메모·이름 없음 */
data class SupportOriginal(
    val studentId: UUID,
    val attemptId: UUID,
    val answers: List<SupportAnswer>,
)

/** text는 시도 상세 AnswerItem.text와 같은 원문, feedback은 피드백 결과와 같은 모양 */
data class SupportAnswer(
    val answerId: UUID,
    val version: Int,
    val text: String,
    val feedback: FeedbackResult,
)
