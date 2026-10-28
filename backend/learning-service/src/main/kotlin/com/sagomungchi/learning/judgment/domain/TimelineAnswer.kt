package com.sagomungchi.learning.judgment.domain

import com.sagomungchi.learning.mission.domain.InputType
import java.time.Instant
import java.util.UUID

/**
 * 시도 타임라인의 답변 한 줄과 판정 처리 상태 (class-diagram 4.1 AttemptService --> JudgmentService : 타임라인).
 * followupQuestion은 이 답변이 답한 되묻기 질문 (되묻기 요청의 타임라인, class-diagram 4.2 FeedbackFacade --> AttemptService : 타임라인)
 */
data class TimelineAnswer(
    val answerId: UUID,
    val version: Int,
    val submittedAt: Instant,
    val inputType: InputType,
    val text: String?,
    val followupId: UUID?,
    val followupQuestion: String?,
    val content: Map<String, Any?>,
    val processStatus: ProcessStatus,
)

/** 판정 처리 상태 (api-spec 1.5). 보류(HELD)는 결과, 실패(FAILED)는 처리 상태로 구분 */
enum class ProcessStatus { PENDING, RUNNING, DONE, FAILED }
