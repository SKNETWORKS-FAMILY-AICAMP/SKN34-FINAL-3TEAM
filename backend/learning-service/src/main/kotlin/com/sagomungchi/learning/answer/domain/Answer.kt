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
    /** 생각·작성 시간(초, P28). 재지 못했거나 저장하지 않는 답은 둘 다 null (AnswerTime) */
    val thinkingSeconds: Int? = null,
    val writingSeconds: Int? = null,
) {
    /**
     * 같은 Idempotency-Key의 재요청이 최초 요청과 같은 내용인지.
     * 생각·작성 시간은 비교하지 않는다: 다시 보낸 답이 같으면 시간만 달라도 같은 요청이고 처음 저장한 시간을 그대로 둔다 (#801)
     */
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
            time: AnswerTime? = null,
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
            thinkingSeconds = time?.thinkingSeconds,
            writingSeconds = time?.writingSeconds,
        )
    }
}
