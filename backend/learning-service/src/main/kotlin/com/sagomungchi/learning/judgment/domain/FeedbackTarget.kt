package com.sagomungchi.learning.judgment.domain

import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.mission.domain.InputType
import java.util.UUID

/** 판정할 답변 (answer 행). plainText는 판정·되묻기에 보내는 원문 */
data class FeedbackTarget(
    val answerId: UUID,
    val attemptId: UUID,
    val version: Int,
    val inputType: InputType,
    val content: AnswerContent,
    val plainText: String,
)

/**
 * 저장된 판정 (피드백 결과 재구성용). versions 표기는 시도의 미션·기준표 버전.
 * attemptOpen은 읽는 지금 시도가 답변을 받는지(완료·마무리 전): 다음 행동은 지금 상태로 정함 (FN-JDG-09)
 */
data class StoredJudgment(
    val answerId: UUID,
    val judgmentId: UUID,
    val attemptId: UUID,
    val attemptOpen: Boolean,
    val status: ProcessStatus,
    val result: JudgmentResult?,
    val trial: Boolean?,
    val heldReason: String?,
    val modelVersion: String?,
    val promptVersion: String?,
    val missionLabel: String,
    val rubricLabel: String,
)

data class StoredElement(
    val answerId: UUID,
    val elementId: UUID,
    val label: String,
    val satisfied: Boolean,
    val quote: String?,
    val sourceType: ElementSource?,
) {
    fun view() = ElementView(elementId, label, satisfied, quote, sourceType)
}

data class StoredFollowup(
    val answerId: UUID,
    val followupId: UUID,
    val type: FollowupType,
    val question: String,
    val source: FollowupSource,
) {
    fun view() = FollowupView(followupId, type, question, source)
}
