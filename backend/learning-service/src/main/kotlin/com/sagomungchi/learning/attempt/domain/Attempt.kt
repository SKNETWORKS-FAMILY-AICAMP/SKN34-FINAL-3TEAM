package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import org.springframework.http.HttpStatus
import java.time.Instant
import java.util.UUID

/**
 * 학습 시도 (ERD 4.2). 시작 시점의 미션·기준표 버전을 고정 (NFR-DAT-02).
 * NOT_STARTED는 행이 없는 상태라 값으로 두지 않음 (state-diagram 3.2).
 */
data class Attempt(
    val id: UUID,
    val studentId: UUID,
    val missionId: UUID,
    val missionVersionId: UUID,
    val rubricVersionId: UUID,
    val grade: Int,
    val status: AttemptStatus,
    val startedAt: Instant,
    val finishedAt: Instant?,
    val completedAt: Instant?,
    val updatedAt: Instant,
) {
    /** 완료된 시도에는 답변·초안·도움·돌아보기 쓰기 불가 (state-diagram 3.2) */
    fun requireOpen() {
        if (status == AttemptStatus.COMPLETED) {
            throw BusinessException(HttpStatus.CONFLICT, "ATTEMPT_CLOSED", "완료된 학습 시도")
        }
    }

    /** 답변 제출 가능: 완료뿐 아니라 마무리(finished_at) 뒤에도 409 (P04, state-diagram 3.2). 돌아보기는 마무리 뒤에 하므로 requireOpen과 나눔 */
    fun requireAnswerable() {
        requireOpen()
        if (finishedAt != null) {
            throw BusinessException(HttpStatus.CONFLICT, "ATTEMPT_CLOSED", "마무리한 학습 시도", "마무리 뒤에는 답변을 제출할 수 없음")
        }
    }

    companion object {
        fun start(
            studentId: UUID,
            missionId: UUID,
            versions: MissionSnapshot,
            grade: Int,
            now: Instant,
        ) = Attempt(
            id = UUID.randomUUID(),
            studentId = studentId,
            missionId = missionId,
            missionVersionId = versions.missionVersionId,
            rubricVersionId = versions.rubricVersionId,
            grade = grade,
            status = AttemptStatus.IN_PROGRESS,
            startedAt = now,
            finishedAt = null,
            completedAt = null,
            updatedAt = now,
        )
    }
}

enum class AttemptStatus { IN_PROGRESS, COMPLETED }

