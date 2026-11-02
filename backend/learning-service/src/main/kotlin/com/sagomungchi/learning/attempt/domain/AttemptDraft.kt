package com.sagomungchi.learning.attempt.domain

import java.time.Instant
import java.util.UUID

/**
 * 시도당 1행인 답변 초안 (ERD 4.2). version이 ETag, 저장마다 +1 (state-diagram 3.2).
 * 시도를 만들 때 버전 0의 빈 초안을 함께 만들어 저장은 항상 버전 조건부 UPDATE (sequence-diagram 3.1).
 */
data class AttemptDraft(
    val attemptId: UUID,
    val version: Int,
    val content: DraftContent,
    val savedAt: Instant,
) {
    /** 아직 한 번도 저장하지 않은 초안 (savedAt은 시작 시각이라 저장 시점으로 보여 주지 않음) */
    val neverSaved: Boolean get() = version == INITIAL_VERSION

    fun update(content: DraftContent, now: Instant) =
        copy(version = version + 1, content = content, savedAt = now)

    companion object {
        const val INITIAL_VERSION = 0

        fun empty(attemptId: UUID, now: Instant) =
            AttemptDraft(attemptId, INITIAL_VERSION, DraftContent(emptyMap(), ""), now)
    }
}

/**
 * 초안 내용 (api-spec 2.2 `content: {answer, memo}`). answer는 입력 방식별 작성 중 내용이라 형식을 검사하지 않음
 * (제출 검증은 #24). memo는 학생 본인 조회에만 포함 (P05).
 */
data class DraftContent(
    val answer: Map<String, Any?>,
    val memo: String,
)
