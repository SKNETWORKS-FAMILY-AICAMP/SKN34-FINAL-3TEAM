package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import java.time.Instant
import java.time.LocalDate
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
    /** 시작 경로 (P23, #385). 테마 컨텍스트면 그 주 테마와 주 시작일(KST 월요일)을 함께 저장 */
    val context: AttemptContext = AttemptContext.EXTRA,
    val themeId: UUID? = null,
    val themeWeekStart: LocalDate? = null,
) {
    /** 아직 답변을 받는 시도 (완료·마무리 전). 되묻기 생성과 다음 행동 안내에 씀 (P04) */
    val acceptsAnswers: Boolean get() = status == AttemptStatus.IN_PROGRESS && finishedAt == null

    /** 완료된 시도에는 답변·초안·도움·돌아보기 쓰기 불가 (state-diagram 3.2) */
    fun requireOpen() {
        if (status == AttemptStatus.COMPLETED) {
            throw DomainException(ErrorKind.CONFLICT, "ATTEMPT_CLOSED", "완료된 학습 시도")
        }
    }

    /** 답변 제출 가능: 완료뿐 아니라 마무리(finished_at) 뒤에도 409 (P04, state-diagram 3.2). 돌아보기는 마무리 뒤에 하므로 requireOpen과 나눔 */
    fun requireAnswerable() {
        requireOpen()
        if (finishedAt != null) {
            throw DomainException(ErrorKind.CONFLICT, "ATTEMPT_CLOSED", "마무리한 학습 시도", "마무리 뒤에는 답변을 제출할 수 없음")
        }
    }

    /**
     * 마무리 (state-diagram 3.2 작성 → 마무리됨). 마무리 조건(FinishPolicy.canFinish)은 부른 쪽이 타임라인으로 먼저 확인 (sequence-diagram 3.3).
     * 완료된 시도는 409 ATTEMPT_CLOSED
     */
    fun finish(now: Instant): Attempt {
        requireOpen()
        check(finishedAt == null) { "이미 마무리한 시도" }
        return copy(finishedAt = now, updatedAt = now)
    }

    /** 돌아보기 저장 시 학습 완료 (state-diagram 3.2 IN_PROGRESS → COMPLETED, FN-LRN-14) */
    fun complete(now: Instant): Attempt {
        requireFinished()
        return copy(status = AttemptStatus.COMPLETED, completedAt = now, updatedAt = now)
    }

    /**
     * 마무리 뒤에 하는 쓰기(돌아보기·자기 평가): 완료된 시도는 409 ATTEMPT_CLOSED,
     * 마무리 전이면 409 REVEAL_CONDITION_UNMET (state-diagram 3.2·9장)
     */
    fun requireFinished() {
        requireOpen()
        if (finishedAt == null) {
            throw DomainException(ErrorKind.CONFLICT, "REVEAL_CONDITION_UNMET", "마무리 전", "마무리한 뒤에 할 수 있어요.")
        }
    }

    companion object {
        fun start(
            studentId: UUID,
            missionId: UUID,
            versions: MissionSnapshot,
            grade: Int,
            now: Instant,
            context: AttemptContext = AttemptContext.EXTRA,
            theme: ThemeAttempt? = null,
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
            context = context,
            themeId = theme?.themeId,
            themeWeekStart = theme?.weekStart,
        ).also {
            require((context == AttemptContext.EXTRA) == (theme == null)) { "테마 컨텍스트에만 테마가 있음" }
        }
    }
}

enum class AttemptStatus { IN_PROGRESS, COMPLETED }

/**
 * 시도 시작 경로 (P23, api-spec 2.11). THEME_DAY는 오늘 요일 테마 문제, THEME_REVIEW는 토·일 되돌아보기 다시 풀기,
 * EXTRA는 생각 유형별 고르기(테마 밖). 요청에서 생략하면 EXTRA
 */
enum class AttemptContext { THEME_DAY, THEME_REVIEW, EXTRA }

/** 테마 시도에 고정할 그 주 테마 (테마 시작 검사 결과) */
data class ThemeAttempt(val themeId: UUID, val weekStart: LocalDate)

