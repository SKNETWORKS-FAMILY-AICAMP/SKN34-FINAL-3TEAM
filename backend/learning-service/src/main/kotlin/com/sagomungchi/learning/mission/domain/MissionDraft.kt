package com.sagomungchi.learning.mission.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import java.time.Instant
import java.util.UUID

/** 미션 초안 상태 (state-diagram 3.4, #353) */
enum class DraftStatus { GENERATING, READY, CHECK_FAILED, FAILED, ADOPTED, DISCARDED }

/** 검사 실패 사유. check는 ai REQUIRED·QUESTION_LENGTH·LEAK, learning STANDARD_CODE·ELEMENT_CODE·SHAPE, AI 호출 실패 AI_CALL */
data class DraftFailure(val check: String, val reason: String)

/** check_results 한 줄: 시도 번호와 그 시도의 실패 */
data class DraftAttemptFailures(val attempt: Int, val failures: List<DraftFailure>)

/** 초안 요청 입력 (api-spec 4.1 MissionDraft.input). achievementLevels는 성취기준별 단계, 없으면 null */
data class DraftInput(
    val standardCodes: List<String>,
    val achievementLevels: Map<String, String>?,
    val thinkingType: ThinkingType,
    val gradeMin: Int,
    val gradeMax: Int,
    val inputType: InputType,
)

data class DraftVersions(val prompt: String?, val model: String?)

/** ai가 만든 초안 요소 (api-spec 4.2 draft.elements) */
data class GeneratedElement(
    val code: String,
    val label: String,
    val description: String,
    val goodThought: Boolean,
    val standardCode: String?,
)

/** ai가 만든 초안 (api-spec 4.2 `draft`). sceneNote는 그림 제작 메모로 초안에만 둠 */
data class GeneratedDraft(
    val title: String,
    val question: String,
    val guide: String?,
    val sceneNote: String?,
    val choices: List<Choice>?,
    val categories: List<Category>?,
    val answerKey: AnswerKey?,
    val exampleAnswer: String?,
    val forbiddenTerms: List<String>,
    val hints: List<String>,
    val elements: List<GeneratedElement>,
)

/** 생성 1회 결과 */
sealed interface DraftAttempt {
    /** ai·learning 검사 통과 */
    data class Passed(val draft: GeneratedDraft, val versions: DraftVersions) : DraftAttempt

    /** 초안은 만들었지만 검사 실패 */
    data class CheckFailed(val draft: GeneratedDraft, val failures: List<DraftFailure>, val versions: DraftVersions) : DraftAttempt

    /** AI 호출 실패 (failureCode는 판정과 같은 AI_*) */
    data class AiFailed(val failureCode: String) : DraftAttempt
}

/**
 * 미션 초안 (class-diagram 4.1.1, ERD 4.1 mission_draft, state-diagram 3.4). 생성은 주기 작업이 리스를 잡고 1회씩,
 * 반복·상한은 여기서 정한다. 학생 정보는 없다
 */
class MissionDraft(
    val id: UUID,
    val requestedBy: UUID,
    val input: DraftInput,
    status: DraftStatus,
    attempts: Int,
    checkResults: List<DraftAttemptFailures>,
    output: GeneratedDraft?,
    failureCode: String?,
    versions: DraftVersions,
    leaseUntil: Instant?,
    missionId: UUID?,
    val createdAt: Instant,
    updatedAt: Instant,
) {
    var status: DraftStatus = status
        private set
    var attempts: Int = attempts
        private set
    var checkResults: List<DraftAttemptFailures> = checkResults
        private set
    var output: GeneratedDraft? = output
        private set
    var failureCode: String? = failureCode
        private set
    var versions: DraftVersions = versions
        private set
    var leaseUntil: Instant? = leaseUntil
        private set
    var missionId: UUID? = missionId
        private set
    var updatedAt: Instant = updatedAt
        private set

    /** 다음 생성에 넣을 이전 실패 사유 (겹치는 것은 한 번) */
    val previousFailures: List<DraftFailure>
        get() = checkResults.flatMap { it.failures }.distinct()

    /**
     * 생성 1회 기록 (class-diagram 4.1.1 recordAttempt). attempts + 1, 리스를 비움.
     * 통과면 READY. 실패면 사유를 쌓고 상한 미만이면 GENERATING 그대로(다음 주기에 다시 생성),
     * 상한이면 마지막 실패가 AI 호출이면 FAILED, 아니면 CHECK_FAILED
     */
    fun recordAttempt(result: DraftAttempt, maxAttempts: Int, now: Instant) {
        if (status != DraftStatus.GENERATING) conflict("생성 중이 아님")
        attempts += 1
        leaseUntil = null
        updatedAt = now
        when (result) {
            is DraftAttempt.Passed -> {
                output = result.draft
                versions = result.versions
                failureCode = null
                status = DraftStatus.READY
            }
            is DraftAttempt.CheckFailed -> {
                output = result.draft
                versions = result.versions
                failureCode = null
                checkResults = checkResults + DraftAttemptFailures(attempts, result.failures)
                if (attempts >= maxAttempts) status = DraftStatus.CHECK_FAILED
            }
            is DraftAttempt.AiFailed -> {
                failureCode = result.failureCode
                checkResults = checkResults + DraftAttemptFailures(attempts, listOf(DraftFailure(AI_CALL, result.failureCode)))
                if (attempts >= maxAttempts) status = DraftStatus.FAILED
            }
        }
    }

    /** READY만 채택 (미션을 만들기 전에 확인) */
    fun requireAdoptable() {
        if (status != DraftStatus.READY) conflict("채택할 수 없는 상태")
    }

    /** READY만 채택 → ADOPTED + 만든 미션 */
    fun adopt(missionId: UUID, now: Instant) {
        requireAdoptable()
        status = DraftStatus.ADOPTED
        this.missionId = missionId
        updatedAt = now
    }

    /** READY·CHECK_FAILED·FAILED만 버림 */
    fun discard(now: Instant) {
        if (status !in DISCARDABLE) conflict("버릴 수 없는 상태")
        status = DraftStatus.DISCARDED
        updatedAt = now
    }

    private fun conflict(detail: String): Nothing =
        throw DomainException(ErrorKind.CONFLICT, "CONFLICT", "초안 상태 충돌", "$detail: $status")

    companion object {
        const val AI_CALL = "AI_CALL"
        private val DISCARDABLE = setOf(DraftStatus.READY, DraftStatus.CHECK_FAILED, DraftStatus.FAILED)
    }
}

/** 초안 목록 (api-spec 1.1 봉투) */
data class DraftPage(val items: List<MissionDraft>, val page: Int, val size: Int, val totalElements: Long)
