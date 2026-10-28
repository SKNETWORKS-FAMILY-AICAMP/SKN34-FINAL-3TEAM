package com.sagomungchi.learning.answer.domain

import com.sagomungchi.learning.mission.domain.InputType
import java.time.Instant
import java.util.UUID

/**
 * 제출 답변 (ERD 4.2). 덮어쓰지 않고 버전마다 추가 (FN-LRN-08~10).
 * 보완 답변은 답한 되묻기(followupId)와 이전 답변에 연결
 */
data class Answer(
    val id: UUID,
    val attemptId: UUID,
    val version: Int,
    val followupId: UUID?,
    val previousAnswerId: UUID?,
    val inputType: InputType,
    val content: AnswerContent,
    val plainText: String?,
    val dictatedByGuardian: Boolean,
    val idempotencyKey: UUID,
    val submittedAt: Instant,
) {
    /** 같은 Idempotency-Key의 재요청이 최초 요청과 같은 내용인지 */
    fun sameRequestAs(other: Answer) =
        inputType == other.inputType && content == other.content &&
            followupId == other.followupId && dictatedByGuardian == other.dictatedByGuardian

    companion object {
        /** class-diagram 4.1 Answer.next: 이전 답변 다음 버전 */
        fun next(
            previous: Answer?,
            attemptId: UUID,
            followupId: UUID?,
            inputType: InputType,
            content: AnswerContent,
            plainText: String,
            dictatedByGuardian: Boolean,
            idempotencyKey: UUID,
            now: Instant,
        ) = Answer(
            id = UUID.randomUUID(),
            attemptId = attemptId,
            version = (previous?.version ?: 0) + 1,
            followupId = followupId,
            previousAnswerId = previous?.id,
            inputType = inputType,
            content = content,
            plainText = plainText,
            dictatedByGuardian = dictatedByGuardian,
            idempotencyKey = idempotencyKey,
            submittedAt = now,
        )
    }
}
