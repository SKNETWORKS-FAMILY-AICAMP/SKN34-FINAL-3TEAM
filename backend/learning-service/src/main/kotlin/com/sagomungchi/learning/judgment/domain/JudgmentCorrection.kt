package com.sagomungchi.learning.judgment.domain

import java.time.Instant
import java.util.UUID

/** 정정 요청 (api-spec 4.1, core #46). correctedBy는 core가 검증한 관리자 ID(X-User-Id) */
data class CorrectionCommand(
    val reportId: UUID,
    val reason: String,
    val corrected: JudgmentResult,
    val correctedBy: UUID,
)

/**
 * 판정 정정 (ERD 4.2 judgment_correction, FN-SUP-03). 판정·요소·답변은 그대로 두고 이 행을 추가하고,
 * 조회 때 최신 정정 결과를 judgment.result로 보여 줌 (class-diagram 4.2). previous는 정정 직전에 보이던 결과
 */
data class JudgmentCorrection(
    val id: UUID,
    val judgmentId: UUID,
    val reportId: UUID,
    val reason: String,
    val previous: JudgmentResult,
    val corrected: JudgmentResult,
    val correctedBy: UUID,
    val idempotencyKey: UUID,
    val createdAt: Instant,
) {
    /** 같은 키 재요청이 처음과 같은 요청(판정·본문)인지. 정정한 관리자는 비교하지 않음 */
    fun isSameRequest(judgmentId: UUID, command: CorrectionCommand): Boolean =
        this.judgmentId == judgmentId && reportId == command.reportId && reason == command.reason && corrected == command.corrected
}

/** 정정할 판정 (잠근 judgment 행). result는 지금 보이는 결과(최신 정정이 있으면 그 결과) */
data class CorrectionTarget(
    val judgmentId: UUID,
    val studentId: UUID,
    val status: ProcessStatus,
    val result: JudgmentResult?,
)
