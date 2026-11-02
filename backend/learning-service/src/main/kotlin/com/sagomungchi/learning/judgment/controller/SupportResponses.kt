package com.sagomungchi.learning.judgment.controller

import com.fasterxml.jackson.annotation.JsonInclude
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.SupportTarget
import java.util.UUID

/** 신고·문의 대상 (api-spec 4.1, #146). 없는 칸은 응답에서 뺌(core 계약은 선택 칸) */
@JsonInclude(JsonInclude.Include.NON_NULL)
data class SupportTargetResponse(
    val studentId: UUID,
    val attemptId: UUID,
    val judgmentId: UUID?,
    val previousResult: JudgmentResult?,
) {
    companion object {
        fun from(target: SupportTarget) =
            SupportTargetResponse(target.studentId, target.attemptId, target.judgmentId, target.previousResult)
    }
}
