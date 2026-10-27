package com.sagomungchi.learning.attempt.controller

import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.domain.HintOpened
import com.sagomungchi.learning.attempt.service.AttemptDetail
import com.sagomungchi.learning.mission.controller.MissionResponse
import java.time.Instant
import java.util.UUID

/** 초안 저장 요청 (api-spec 2.2 `content: {answer, memo}`) */
data class DraftRequest(val content: DraftContent)

/** 초안 (api-spec 3.6). 한 번도 저장하지 않았으면 savedAt 없음 */
data class DraftResponse(
    val version: Int,
    val content: DraftContent,
    val savedAt: Instant?,
) {
    companion object {
        fun from(draft: AttemptDraft) =
            DraftResponse(draft.version, draft.content, draft.savedAt.takeUnless { draft.neverSaved })
    }
}

/**
 * 시도 상세. 필드 이름은 프론트 Attempt 모델(api-spec 3.7·3.8). mission은 시도에 고정된 버전.
 * answers·nextActions는 답변 제출(#24)·피드백(#25) 전이라 빈 목록
 */
data class AttemptResponse(
    val attemptId: UUID,
    val studentId: UUID,
    val mission: MissionResponse,
    val status: AttemptStatus,
    val finishedAt: Instant?,
    val answers: List<Any>,
    val helped: Boolean,
    val draft: DraftResponse,
    val nextActions: List<String>,
) {
    companion object {
        fun from(detail: AttemptDetail) = AttemptResponse(
            attemptId = detail.attempt.id,
            studentId = detail.attempt.studentId,
            mission = MissionResponse.from(detail.mission),
            status = detail.attempt.status,
            finishedAt = detail.attempt.finishedAt,
            answers = emptyList(),
            helped = detail.helped,
            draft = DraftResponse.from(detail.draft),
            nextActions = emptyList(),
        )
    }
}

/** 생각 열기 (프론트는 question만 사용, seq·total은 몇 번째 질문인지 표시용) */
data class HintResponse(
    val question: String,
    val seq: Int,
    val total: Int,
) {
    companion object {
        fun from(opened: HintOpened) = HintResponse(opened.question.content, opened.question.seq, opened.total)
    }
}
